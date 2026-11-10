"""Read-only provider research, explicit approvals, and bounded free-provider failover.

Internet content is evidence only. This service never installs code, creates accounts,
accepts terms, purchases credits, or treats a page as permission to use credentials.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any
from urllib.parse import urlsplit

import httpx

from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_control import (
    RequestCancelledError,
    check_cancelled,
    current_control,
)
from jarvis.models.base import ModelProvider, ModelRequest, ModelResponse
from jarvis.models.retry import retry_guard


@dataclass(frozen=True)
class ProviderSpec:
    source: str
    name: str
    documentation: str
    console: str
    terms: str
    access: str


SPECS = {
    "groq": ProviderSpec("groq", "Groq", "https://console.groq.com/docs/billing-faqs",
                         "https://console.groq.com/keys", "https://console.groq.com/docs/policies-notices", "free_tier"),
    "gemini": ProviderSpec("gemini", "Gemini", "https://ai.google.dev/gemini-api/docs/billing",
                           "https://aistudio.google.com/api-keys", "https://ai.google.dev/gemini-api/terms", "free_tier"),
    "openrouter_free": ProviderSpec("openrouter_free", "OpenRouter free models",
                                    "https://openrouter.ai/docs/guides/routing/routers/free-router",
                                    "https://openrouter.ai/settings/keys", "https://openrouter.ai/terms", "zero_price_catalog"),
    "xai": ProviderSpec("xai", "Grok / xAI", "https://docs.x.ai/console/billing",
                        "https://console.x.ai", "https://x.ai/legal/terms-of-service-enterprise", "paid_or_unverified"),
    "openai": ProviderSpec("openai", "OpenAI API", "https://developers.openai.com/api/docs/pricing",
                           "https://platform.openai.com/api-keys", "https://openai.com/policies/business-terms/", "paid_or_unverified"),
}
CATALOG_URL = "https://openrouter.ai/api/v1/models"
ALLOWED_HOSTS = {urlsplit(spec.documentation).hostname for spec in SPECS.values()} | {"openrouter.ai"}
REVIEW_TTL = 7 * 86400


class ProviderApprovalError(ValueError):
    pass


class ProviderSteward:
    def __init__(self, memory: PersonalMemory, transport: httpx.BaseTransport | None = None) -> None:
        self.memory = memory
        self.transport = transport
        self._lock = RLock()

    def policy(self) -> dict[str, Any]:
        records = self.memory.records("provider_policy")
        return records[0] if records else {
            "enabled": False, "auto_review": True, "commercial": False,
            "allow_failover": False, "daily_limit": 100,
        }

    def configure(self, *, enabled: bool, auto_review: bool, commercial: bool,
                  allow_failover: bool, daily_limit: int) -> None:
        if not 1 <= daily_limit <= 5000:
            raise ValueError("Choose a daily request limit between 1 and 5000.")
        self.memory.save_record("provider_policy", "main", {
            "enabled": enabled or commercial, "auto_review": auto_review,
            "commercial": commercial, "allow_failover": allow_failover, "daily_limit": daily_limit,
        })

    def offers(self) -> list[dict[str, Any]]:
        return self.memory.records("provider_offer")

    def offer(self, source: str) -> dict[str, Any]:
        return next((o for o in self.offers() if o["source"] == source), {})

    def approval(self, source: str) -> dict[str, Any]:
        return next((a for a in self.memory.records("provider_approval") if a["source"] == source), {})

    def review_due(self) -> bool:
        last = max((float(o.get("attempted_at", 0)) for o in self.offers()), default=0)
        return time.time() - last >= 86400

    def _fetch(self, client: httpx.Client, url: str, limit: int = 2_000_000) -> bytes:
        # No credentials are attached to research requests, and redirects are not trusted.
        for _ in range(3):
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.port not in {None, 443}:
                raise ValueError("Research URL is outside the reviewed provider list.")
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    url = str(response.url.join(location))
                    continue
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError("Provider research response exceeded its size limit.")
                return bytes(data)
        raise ValueError("Provider documentation redirected too many times.")

    @staticmethod
    def _document_text(raw: bytes) -> str:
        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        main = re.search(r"<(?:main|article)\b[^>]*>(.*?)</(?:main|article)>", text, re.IGNORECASE | re.DOTALL)
        if main:
            text = main[1]
        return " ".join(re.sub(r"<[^>]+>", " ", text).split())

    @staticmethod
    def free_models(payload: object) -> list[dict[str, str]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise TypeError("Invalid model catalog.")
        models = []
        for raw in payload["data"]:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                continue
            prices = raw.get("pricing")
            if not isinstance(prices, dict) or any(k not in prices for k in ("prompt", "completion")):
                continue
            try:
                if not prices or any(not Decimal(str(v)).is_finite() or Decimal(str(v)) != 0 for v in prices.values()):
                    continue
            except (InvalidOperation, ValueError):
                continue
            if raw["id"].endswith(":free"):
                models.append({"id": raw["id"][:250], "name": str(raw.get("name", raw["id"]))[:200]})
        return sorted(models, key=lambda m: m["id"])

    def review(self) -> list[dict[str, Any]]:
        def inspect(spec: ProviderSpec) -> dict[str, Any]:
            previous = self.offer(spec.source)
            try:
                with httpx.Client(timeout=httpx.Timeout(12, connect=5), transport=self.transport,
                                  headers={"User-Agent": "Jarvis-Provider-Review/0.1"}) as client:
                    text = self._document_text(self._fetch(client, spec.documentation))
                    if len(text) < 80:
                        raise ValueError("Documentation did not contain enough readable evidence.")
                    models = self.free_models(json.loads(self._fetch(client, CATALOG_URL, 8_000_000))) if spec.source == "openrouter_free" else []
                # A new free model need not revoke an approved free-router connection.
                # Selected individual models are still rechecked against every refreshed catalog.
                revision = hashlib.sha256(text.encode()).hexdigest()
                offer = {"source": spec.source, "name": spec.name, "access": spec.access,
                         "documentation": spec.documentation, "terms": spec.terms, "console": spec.console,
                         "checked_at": time.time(), "attempted_at": time.time(), "revision": revision,
                         "models": models, "model_count": len(models), "error": "",
                         "summary": ("Zero-price models found in the current public catalog. Limits still apply."
                                     if spec.access == "zero_price_catalog" else
                                     "A free tier may apply to your account; confirm billing status and terms before activation."
                                     if spec.access == "free_tier" else
                                     "Paid or unverified access. Not eligible for this free-provider policy.")}
            except (httpx.HTTPError, ValueError, TypeError):
                offer = {**previous, "source": spec.source, "name": spec.name, "access": spec.access,
                         "documentation": spec.documentation, "terms": spec.terms, "console": spec.console,
                         "attempted_at": time.time(), "error": "Could not refresh official evidence. Previous approval is usable only while its review remains fresh."}
            self.memory.save_record("provider_offer", spec.source, offer)
            return offer
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="provider-review") as pool:
            return list(pool.map(inspect, SPECS.values()))

    def _fresh_offer(self, source: str) -> dict[str, Any]:
        offer = self.offer(source)
        if not offer.get("revision") or time.time() - float(offer.get("checked_at", 0)) > REVIEW_TTL:
            raise ProviderApprovalError("Refresh official provider research before approving or using this connection.")
        return offer

    def approve_connection(self, source: str, *, free_account_confirmed: bool,
                           terms_reviewed: bool, allow_fallback: bool = False) -> None:
        if not self.policy()["enabled"]:
            raise ProviderApprovalError("Enable the API assistant first.")
        offer = self._fresh_offer(source)
        if source not in SPECS or SPECS[source].access == "paid_or_unverified":
            raise ProviderApprovalError("This assistant does not enroll paid APIs or spend credits.")
        if not free_account_confirmed or not terms_reviewed:
            raise ProviderApprovalError("Confirm the account's free tier and review its terms for your intended use.")
        if source == "openrouter_free" and not offer.get("models"):
            raise ProviderApprovalError("No verified zero-price model catalog is available.")
        self.memory.save_record("provider_approval", source, {
            "source": source, "revision": offer["revision"], "approved_at": time.time(),
            "expires_at": time.time() + REVIEW_TTL, "commercial": self.policy()["commercial"],
            "fallback_allowed": allow_fallback, "model": "", "active": False,
        })

    def require_connection(self, source: str) -> dict[str, Any]:
        offer = self._fresh_offer(source)
        approval = self.approval(source)
        if (not approval or approval.get("revision") != offer.get("revision")
                or float(approval.get("expires_at", 0)) <= time.time()
                or bool(approval.get("commercial")) != bool(self.policy()["commercial"])):
            raise ProviderApprovalError("This connection needs your approval in API assistant. Research, scope, or approval has changed.")
        return approval

    def activate(self, source: str, model: str) -> None:
        approval = self.require_connection(source)
        if not model.strip():
            raise ProviderApprovalError("Choose a model before activation.")
        if (source == "openrouter_free" and model != "openrouter/free"
                and model not in {m["id"] for m in self.offer(source).get("models", [])}):
            raise ProviderApprovalError("This model has no current verified zero-price listing.")
        self.memory.save_record("provider_approval", source, {**approval, "model": model, "active": True})

    def bind_key(self, source: str, fingerprint: str) -> None:
        approval = self.require_connection(source)
        if approval.get("active") and approval.get("key_fingerprint") not in {None, fingerprint}:
            self.revoke(source)
            raise ProviderApprovalError("A different account key needs a new connection approval. The existing key was kept.")
        self.memory.save_record("provider_approval", source, {**approval, "key_fingerprint": fingerprint})

    def revoke(self, source: str) -> None:
        self.memory.save_record("provider_approval", source, {"source": source, "active": False})

    def before_request(self, source: str, model: str, key_fingerprint: str = "") -> None:
        with self._lock:
            approval = self.require_connection(source)
            if not approval.get("active") or model != approval.get("model"):
                raise ProviderApprovalError("Approve and activate this exact model in API assistant first.")
            if approval.get("key_fingerprint") and approval["key_fingerprint"] != key_fingerprint:
                raise ProviderApprovalError("This credential does not match the approved account connection.")
            if (source == "openrouter_free" and model != "openrouter/free"
                    and model not in {m["id"] for m in self.offer(source).get("models", [])}):
                raise ProviderApprovalError("The selected model is no longer verified as zero-price.")
            health = next((h for h in self.memory.records("provider_health") if h.get("source") == source), {})
            if float(str(health.get("retry_at", 0))) > time.time():
                raise ProviderApprovalError("This provider is cooling down after a connection or rate-limit error.")
            day = datetime.now(UTC).date().isoformat()
            usage = next((u for u in self.memory.records("provider_usage")
                          if u.get("source") == source and u.get("day") == day), {})
            count = int(str(usage.get("attempts", 0)))
            if count >= self.policy()["daily_limit"]:
                raise ProviderApprovalError("JARVIS's daily request allowance for this provider is exhausted.")
            self.memory.save_record("provider_usage", f"{day}:{source}", {
                "source": source, "day": day, "attempts": count + 1,
            })

    def record_failure(self, source: str, error: Exception) -> None:
        if isinstance(error, (ProviderApprovalError, RequestCancelledError)):
            return
        code = None
        cause: BaseException | None = error
        for _ in range(5):
            if isinstance(cause, httpx.HTTPStatusError):
                code = cause.response.status_code
                break
            cause = cause.__cause__ if cause else None
        self.memory.save_record("provider_health", source, {
            "source": source, "retry_at": time.time() + (1800 if code == 429 else 300),
            "reason": "rate_limit" if code == 429 else "request_failed",
        })

    def fallback_sources(self, failed: str) -> list[str]:
        if not self.policy()["allow_failover"]:
            return []
        return [str(a["source"]) for a in self.memory.records("provider_approval")
                if a.get("source") != failed and a.get("active") and a.get("fallback_allowed")]


class ManagedProvider(ModelProvider):
    def __init__(self, delegate: ModelProvider, source: str, steward: ProviderSteward,
                 fallback_factory: Callable[[str], ModelProvider], local_provider: ModelProvider | None = None) -> None:
        self.delegate = delegate
        self.source = source
        self.steward = steward
        self.fallback_factory = fallback_factory
        self.local_provider = local_provider
        self._last = delegate
        self.name = delegate.name

    @property
    def model(self) -> str:
        return str(getattr(self._last, "model", "default"))

    @property
    def supports_grounded_planner(self) -> bool:
        return bool(getattr(self.delegate, "supports_grounded_planner", False))

    def _call(self, provider: ModelProvider, source: str, request: ModelRequest) -> ModelResponse:
        check_cancelled()
        key = str(getattr(provider, "api_key", ""))
        def authorize():
            self.steward.before_request(source, str(getattr(provider, "model", "")), hashlib.sha256(key.encode()).hexdigest())
        authorize()
        self._last = provider
        self.name = provider.name
        try:
            with retry_guard(authorize):
                return provider.generate(request)
        except (RequestCancelledError, ProviderApprovalError):
            raise
        except Exception as exc:
            self.steward.record_failure(source, exc)
            raise

    def generate(self, request: ModelRequest) -> ModelResponse:
        try:
            return self._call(self.delegate, self.source, request)
        except RequestCancelledError:
            raise
        except (ValueError, RuntimeError, httpx.HTTPError):
            control = current_control()
            if (not self.steward.policy()["allow_failover"] or request.tools or request.images or request.json_schema is not None
                    or any(m.role == "tool" or m.tool_calls for m in request.messages)
                    or (control is not None and control.first_text_seconds is not None)):
                raise
            for source in self.steward.fallback_sources(self.source):
                try:
                    candidate = self.fallback_factory(source)
                    return self._call(candidate, source, request)
                except RequestCancelledError:
                    raise
                except (ValueError, RuntimeError, httpx.HTTPError):
                    control = current_control()
                    if control is not None and control.first_text_seconds is not None:
                        raise
                    continue
            if self.local_provider is not None:
                check_cancelled()
                self._last = self.local_provider
                self.name = self.local_provider.name
                return self.local_provider.generate(request)
            raise
