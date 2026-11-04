"""Explicit account/API choices, with no silent paid fallback."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from jarvis.core.config import JarvisSettings
from jarvis.core.personal_memory import PersonalMemory
from jarvis.models.base import ModelProvider
from jarvis.models.chatgpt_account import ChatGPTAccount
from jarvis.models.chatgpt_plan import ChatGPTPlanProvider
from jarvis.models.connection_errors import (
    ProviderCooldown,
    check_provider_response,
    network_failure,
)
from jarvis.models.gemini import GeminiProvider
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.runtime.api_usage import ApiUsage
from jarvis.runtime.provider_steward import (
    ManagedProvider,
    ProviderApprovalError,
    ProviderSteward,
)
from jarvis.security.credential_vault import CredentialVault

SOURCES = {
    "auto": "Automatic · local actions + connected AI", "chatgpt_plan": "ChatGPT plan · sign in",
    "groq": "Groq API · free tier available", "gemini": "Gemini API · free tier if eligible",
    "openrouter_free": "OpenRouter · free models only", "openai": "OpenAI API · separate billing",
    "local": "Ollama · local on your PC", "hermes": "Hermes · its configured provider",
}
API_SOURCES = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.1-flash-lite"),
    "openrouter_free": ("https://openrouter.ai/api/v1", "openrouter/free"),
    "openai": ("https://api.openai.com/v1", "gpt-4.1-mini"),
}


class IntelligenceHub:
    def __init__(self, settings: JarvisSettings, memory: PersonalMemory) -> None:
        self.memory = memory
        self.usage = ApiUsage(memory)
        self._balance_cache: dict[str, str] = {}
        self._cooldowns: dict[tuple[str, str, str], ProviderCooldown] = {}
        self.vault = CredentialVault(settings.state_dir if settings.persist_personal_memory else None)
        self.account = ChatGPTAccount(self.vault)
        self.steward = ProviderSteward(memory)
        self.local_fallback: ModelProvider | None = None
        self.environment_keys = {
            "groq": settings.groq_api_key, "gemini": settings.gemini_api_key,
            "openai": settings.openai_api_key, "openrouter_free": settings.openrouter_api_key,
        }
        self.endpoints = {**API_SOURCES,
                          "groq": (settings.groq_base_url, API_SOURCES["groq"][1]),
                          "openai": (settings.openai_base_url, settings.openai_model),
                          "openrouter_free": (settings.openrouter_base_url, "openrouter/free")}

    def usage_report(self, source: str, *, refresh: bool = False) -> str:
        report = self.usage.report(source, self.api_key(source))
        identity = self.usage.identity(source, self.api_key(source))
        if not refresh or source != "openrouter_free":
            return report + self._balance_cache.get(identity, "")
        key = self.api_key(source)
        if not key:
            raise ValueError("Save this provider's key first.")
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
            check_provider_response(response, source)
        except httpx.RequestError as exc:
            raise network_failure(source, exc) from exc
        data = response.json().get("data", {})
        remaining = data.get("limit_remaining")
        usage = data.get("usage")
        extra = (f"\nOpenRouter key spending cap remaining (USD): {remaining}" if isinstance(remaining, (int, float)) else
                         "\nOpenRouter: no numeric key spending cap returned. This does not mean unlimited free requests.") + (
                         f"\nProvider-reported key usage (USD): {usage}" if isinstance(usage, (int, float)) else "")
        self._balance_cache[identity] = extra + "\nBalance is a snapshot from the last explicit refresh this session."
        return report + self._balance_cache[identity]

    def preferences(self) -> dict[str, Any]:
        records = self.memory.records("intelligence")
        return records[0] if records else {"source": "auto", "model": "", "concise": True, "theme": "dark"}

    def save_preferences(self, source: str, model: str, concise: bool, theme: str) -> None:
        if source not in SOURCES or theme not in {"light", "dark"}:
            raise ValueError("Choose a supported connection and appearance.")
        if source == "openrouter_free" and model and not self._free_model(model):
            raise ValueError("Free-only mode accepts openrouter/free or model IDs ending in :free.")
        policy = self.steward.policy()
        if source == "chatgpt_plan" and policy["commercial"]:
            raise ProviderApprovalError("Personal ChatGPT plan usage is excluded from product mode. Commercial access needs a separate supported agreement.")
        if policy["enabled"] and source in API_SOURCES:
            approval = self.steward.require_connection(source)
            selected_model = model.strip() or self.model_for(source)
            if not approval.get("active") or approval.get("model") != selected_model:
                raise ProviderApprovalError("Test and enable this exact model in API assistant before selecting it.")
        if policy["enabled"] and source == "hermes":
            raise ProviderApprovalError("Hermes has separate billing/configuration. Use an approved direct connection or local model while API management is enabled.")
        self.memory.save_record("intelligence", "main", {
            "source": source, "model": model.strip(), "concise": concise, "theme": theme,
        })
        if source in {"gemini", "groq", "openrouter_free"} and model.strip():
            self.memory.save_record("automatic_connection", "preferred", {"source": source})
        if model.strip():
            self.memory.save_record("source_models", source, {"source": source, "model": model.strip()})

    def automatic_connection(self) -> tuple[str, str] | None:
        """Use a previously selected free-tier connection, never a newly found key.

        Automatic dispatch is an initial route, not a retry/fallback policy. Paid
        APIs and personal plan access require explicit selection. Managed mode
        additionally requires an active approval for the exact model.
        """
        choices = {str(r["source"]): str(r["model"]) for r in self.memory.records("source_models")
                   if r.get("source") in {"gemini", "groq", "openrouter_free"} and r.get("model")}
        preferred = self.memory.records("automatic_connection")
        order = ([str(preferred[0]["source"])] if preferred else []) + ["gemini", "groq", "openrouter_free"]
        for source in dict.fromkeys(order):
            if not self.api_key(source):
                continue
            if self.steward.policy()["enabled"]:
                try:
                    approval = self.steward.require_connection(source)
                except ProviderApprovalError:
                    continue
                if not approval.get("active"):
                    continue
                return source, str(approval["model"])
            if source in choices:
                return source, choices[source]
        return None

    def model_for(self, source: str) -> str:
        return next((str(record["model"]) for record in self.memory.records("source_models")
                     if record.get("source") == source), self.endpoints.get(source, ("", ""))[1])

    @staticmethod
    def _free_model(model: str) -> bool:
        return model == "openrouter/free" or model.endswith(":free")

    def api_key(self, source: str) -> str:
        saved = self.vault.get("api_keys").get(source)
        if self.steward.policy()["commercial"]:
            return saved or ""  # Never distribute the developer's environment credentials.
        return saved or self.environment_keys.get(source) or ""

    def save_api_key(self, source: str, key: str) -> None:
        if source not in API_SOURCES:
            raise ValueError("Select an API provider first.")
        if self.steward.policy()["enabled"] and key.strip():
            self.steward.require_connection(source)
            self.steward.bind_key(source, hashlib.sha256(key.strip().encode()).hexdigest())
        keys = self.vault.get("api_keys")
        if key.strip():
            keys[source] = key.strip()
        else:
            keys.pop(source, None)
            self.steward.revoke(source)
        self.vault.set("api_keys", keys)

    def provider(self, source: str | None = None, model: str = "", *, managed: bool = True) -> ModelProvider:
        prefs = self.preferences()
        source = str(source or prefs["source"])
        model = model or (prefs.get("model", "") if source == prefs["source"] else "") or self.model_for(source)
        if source == "chatgpt_plan":
            if self.steward.policy()["commercial"]:
                raise ProviderApprovalError("Your personal ChatGPT plan is not a shared backend for customers.")
            return ChatGPTPlanProvider(self.account, model)
        if source not in API_SOURCES:
            raise ValueError("Choose an API or ChatGPT plan connection in Settings.")
        endpoint, default = self.endpoints[source]
        model = model or default
        if source == "openrouter_free" and not self._free_model(model):
            raise ValueError("This connection only allows free OpenRouter models.")
        key = self.api_key(source)
        if not key:
            raise ValueError(f"Connect {SOURCES[source]} in Settings first.")
        provider_class = GeminiProvider if source == "gemini" else OpenAICompatibleProvider
        provider = provider_class(provider_name=source, model=model, base_url=endpoint, api_key=key)
        provider.usage_callback = lambda usage, headers: self.usage.record(source, key, usage, headers)
        if isinstance(provider, OpenAICompatibleProvider):
            identity = (source, model, hashlib.sha256(key.encode()).hexdigest())
            provider.cooldown = self._cooldowns.setdefault(identity, provider.cooldown)
        if isinstance(provider, GeminiProvider):
            provider.fast_replies = bool(prefs.get("concise", True))
        return self.guard_runtime_provider(provider) if managed else provider

    def guard_runtime_provider(self, provider: ModelProvider) -> ModelProvider:
        policy = self.steward.policy()
        if provider.name == "chatgpt_plan":
            if policy["commercial"]:
                raise ProviderApprovalError("Personal ChatGPT plan access is excluded from product mode.")
            return provider  # Personal plan use is separate and never a free-API fallback.
        if not policy["enabled"] or isinstance(provider, ManagedProvider):
            return provider
        if provider.name in {"ollama", "lm_studio", "local"}:
            return provider
        source = "openrouter_free" if provider.name == "openrouter" else provider.name
        if source not in API_SOURCES:
            raise ProviderApprovalError("This runtime has no reviewed adapter in API assistant.")
        if policy["commercial"]:
            provider = self.provider(source, str(getattr(provider, "model", "")), managed=False)
        return ManagedProvider(
            provider, source, self.steward,
            lambda candidate: self.provider(candidate, str(self.steward.approval(candidate).get("model", "")), managed=False),
            self.local_fallback,
        )

    def activate_managed(self, source: str, model: str) -> None:
        self.steward.require_connection(source)
        fingerprint = hashlib.sha256(self.api_key(source).encode()).hexdigest()
        models = self.list_models(source)
        if model not in {m["id"] for m in models}:
            raise ProviderApprovalError("The provider did not return this model for your account. Load models and choose one of its available IDs.")
        if fingerprint != hashlib.sha256(self.api_key(source).encode()).hexdigest():
            raise ProviderApprovalError("The account key changed during validation. Load the new account's models and retry.")
        self.steward.bind_key(source, fingerprint)
        self.steward.activate(source, model)

    def list_models(self, source: str) -> list[dict[str, str]]:
        if source == "chatgpt_plan":
            if self.steward.policy()["commercial"]:
                raise ProviderApprovalError("Personal ChatGPT connections are excluded from product mode.")
            return self.account.list_models()
        if source not in API_SOURCES:
            return []
        if self.steward.policy()["enabled"]:
            self.steward.require_connection(source)
        provider = self.provider(source, managed=False)
        assert isinstance(provider, OpenAICompatibleProvider)
        try:
            with httpx.Client(timeout=15) as client:
                response = client.get(provider.base_url + "/models", headers={"Authorization": "Bearer " + provider.api_key})
            check_provider_response(response, source)
        except httpx.RequestError as exc:
            raise network_failure(source, exc) from exc
        try:
            data = response.json().get("data")
            if not isinstance(data, list):
                raise TypeError("Missing model catalog")
            models = []
            for raw in data:
                if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                    continue
                model_id = raw["id"].removeprefix("models/") if source == "gemini" else raw["id"]
                models.append({"id": model_id, "name": str(raw.get("name") or model_id)})
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"{source} returned an unreadable model catalog. Try again later.") from exc
        if source == "openrouter_free":
            models = [{"id": "openrouter/free", "name": "Free models router"}] + [
                m for m in models if self._free_model(m["id"])]
        return models
