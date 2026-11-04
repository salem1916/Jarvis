"""Actionable provider failures without leaking URLs, keys, or response bodies."""

import math
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx


class ProviderConnectionError(ValueError, RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after: float | None = None, provider: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.provider = provider


def rate_limit_message(error: ProviderConnectionError) -> str:
    name = {"groq": "Groq", "gemini": "Gemini", "openrouter": "OpenRouter", "openai": "OpenAI"}.get(error.provider, "The AI provider")
    when = (f"Try AI again in {max(1, math.ceil(error.retry_after))} seconds."
            if error.retry_after is not None else "Try AI again after its limit resets.")
    return f"{name} reached its usage limit. {when} Local commands are still available."


class ProviderCooldown:
    """Share a provider's requested wait across adapters for the same connection."""

    def __init__(self):
        self.retry_at = 0.0

    def record(self, error: ProviderConnectionError) -> None:
        if error.status_code == 429 and error.retry_after is not None:
            self.retry_at = max(self.retry_at, time.monotonic() + error.retry_after)

    def check(self, provider: str) -> None:
        remaining = self.retry_at - time.monotonic()
        if remaining > 0:
            raise ProviderConnectionError(f"{provider} is still rate limited.", status_code=429,
                                          retry_after=remaining, provider=provider)


def retry_after_seconds(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            seconds = (date - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0, seconds) if math.isfinite(seconds) else None


def check_provider_response(response: httpx.Response, provider: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        code = response.status_code
        if code == 401:
            advice = "The provider rejected this key. Create a replacement in this provider's console; Groq and Grok / xAI use different keys."
        elif code == 403:
            advice = "Access was denied. Check the key's API restrictions, project permissions, and account or regional eligibility."
        elif code == 404:
            advice = "This model or endpoint is unavailable. Load available models and select an ID returned by this account."
        elif code == 429:
            advice = "Rate limit or quota exhausted. Check the provider's usage page and retry later; enabling billing is not required by JARVIS."
        elif code == 402:
            advice = "The provider requires credits for this request. Choose an eligible free model or another connection."
        elif code in {502, 503, 504}:
            advice = "The provider is temporarily busy or unavailable. Retry later or explicitly choose another available model; your key may still be valid."
        elif code == 400:
            advice = "The provider rejected this request. Load available models and check that the selected model supports this task."
        else:
            advice = "The provider could not complete this request. Try again later or choose another approved connection."
        raise ProviderConnectionError(f"{provider} · HTTP {code}: {advice}", status_code=code, provider=provider,
                                      retry_after=retry_after_seconds(response.headers.get("retry-after", ""))) from exc


def network_failure(provider: str, error: httpx.RequestError) -> ProviderConnectionError:
    if isinstance(error, httpx.ReadTimeout):
        advice = "No reply arrived before the wait limit. The provider may be busy or still processing. Retry later or select another available model."
    elif isinstance(error, httpx.TimeoutException):
        advice = "The connection timed out. Check your internet connection, VPN/proxy, and firewall."
    else:
        advice = "Could not reach the provider. Check your internet connection, VPN/proxy, and firewall."
    return ProviderConnectionError(f"{provider}: {advice}")
