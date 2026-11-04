import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from jarvis.core.config import JarvisSettings
from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_control import RequestControl, request_scope
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolDefinition,
)
from jarvis.runtime.intelligence import IntelligenceHub
from jarvis.runtime.provider_steward import (
    CATALOG_URL,
    ManagedProvider,
    ProviderApprovalError,
    ProviderSteward,
)


def make_steward(limit=100, failover=False):
    steward = ProviderSteward(PersonalMemory())
    steward.configure(enabled=True, auto_review=True, commercial=False,
                      allow_failover=failover, daily_limit=limit)
    for source in ("groq", "gemini", "openrouter_free", "openai"):
        steward.memory.save_record("provider_offer", source, {
            "source": source, "revision": "reviewed", "checked_at": time.time(),
            "models": [{"id": "test:free", "name": "Test"}],
        })
    return steward


def approve(steward, source="groq", model="test", fallback=False):
    steward.approve_connection(source, free_account_confirmed=True,
                               terms_reviewed=True, allow_fallback=fallback)
    steward.bind_key(source, hashlib.sha256(b"key").hexdigest())
    steward.activate(source, model)


class RecordingProvider(ModelProvider):
    def __init__(self, name="groq", model="test", error=False, emit=False):
        self.name, self.model, self.api_key = name, model, "key"
        self.error, self.emit, self.calls = error, emit, 0

    def generate(self, request):
        self.calls += 1
        if self.emit:
            from jarvis.core.request_control import current_control
            control = current_control()
            if control:
                control.emit("partial")
        if self.error:
            raise RuntimeError("test provider failure")
        return ModelResponse(text="reply", provider=self.name, model=self.model)


def test_research_uses_public_allowlisted_sources_and_does_not_approve():
    requests = []
    def handle(request):
        requests.append(request)
        if str(request.url) == CATALOG_URL:
            return httpx.Response(200, json={"data": [{"id": "test:free", "pricing": {"prompt": "0", "completion": "0"}}]})
        return httpx.Response(200, text="<main>" + "Official free tier documentation. " * 10 + "</main>")
    steward = ProviderSteward(PersonalMemory(), httpx.MockTransport(handle))
    offers = steward.review()
    assert len(offers) == 5 and all(not o.get("error") for o in offers)
    assert steward.offer("openrouter_free")["model_count"] == 1
    assert not steward.memory.records("provider_approval")
    assert all("authorization" not in r.headers and "cookie" not in r.headers for r in requests)


def test_redirect_cannot_reach_an_untrusted_host():
    called = []
    def handle(request):
        called.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
    steward = ProviderSteward(PersonalMemory(), httpx.MockTransport(handle))
    assert all(o.get("error") for o in steward.review())
    assert len(called) == 5 and all("127.0.0.1" not in url for url in called)


def test_catalog_requires_all_prices_explicitly_zero():
    rows = [
        {"id": "good:free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "paid:free", "pricing": {"prompt": "0", "completion": "0", "request": "1"}},
        {"id": "unknown:free", "pricing": {"prompt": "0"}},
        {"id": "nan:free", "pricing": {"prompt": "NaN", "completion": "0"}},
        {"id": "not-free", "pricing": {"prompt": "0", "completion": "0"}},
    ]
    assert [m["id"] for m in ProviderSteward.free_models({"data": rows})] == ["good:free"]


@pytest.mark.parametrize("free,terms", [(False, True), (True, False), (False, False)])
def test_both_account_and_terms_confirmation_are_required(free, terms):
    with pytest.raises(ProviderApprovalError):
        make_steward().approve_connection("groq", free_account_confirmed=free, terms_reviewed=terms)


def test_paid_provider_is_not_eligible_for_automatic_free_policy():
    with pytest.raises(ProviderApprovalError, match="paid"):
        make_steward().approve_connection("openai", free_account_confirmed=True, terms_reviewed=True)


def test_approval_does_not_activate_and_blocks_inference():
    steward = make_steward()
    steward.approve_connection("groq", free_account_confirmed=True, terms_reviewed=True)
    provider = RecordingProvider()
    managed = ManagedProvider(provider, "groq", steward, lambda _: provider)
    with pytest.raises(ProviderApprovalError):
        managed.generate(ModelRequest(prompt="hello"))
    assert provider.calls == 0


@pytest.mark.parametrize("change", ["expired", "revision", "scope", "revoke", "wrong_model", "wrong_key"])
def test_request_rechecks_approval_scope_model_and_credential(change):
    steward = make_steward()
    approve(steward)
    model, key = "test", hashlib.sha256(b"key").hexdigest()
    if change == "expired":
        steward.memory.save_record("provider_approval", "groq", {**steward.approval("groq"), "expires_at": 0})
    elif change == "revision":
        steward.memory.save_record("provider_offer", "groq", {**steward.offer("groq"), "revision": "changed"})
    elif change == "scope":
        steward.configure(enabled=True, auto_review=True, commercial=True, allow_failover=False, daily_limit=100)
    elif change == "revoke":
        steward.revoke("groq")
    elif change == "wrong_model":
        model = "other"
    else:
        key = "other"
    with pytest.raises(ProviderApprovalError):
        steward.before_request("groq", model, key)


def test_daily_allowance_is_shared_across_concurrent_workers():
    steward = make_steward(limit=3)
    approve(steward)
    def attempt(_):
        try:
            steward.before_request("groq", "test", hashlib.sha256(b"key").hexdigest())
            return True
        except ProviderApprovalError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(20))) == 3


def test_active_key_replacement_requires_new_approval():
    steward = make_steward()
    approve(steward)
    with pytest.raises(ProviderApprovalError):
        steward.bind_key("groq", "new-key")
    assert not steward.approval("groq")["active"]


def test_removed_free_model_cannot_be_used():
    steward = make_steward()
    approve(steward, "openrouter_free", "test:free")
    steward.memory.save_record("provider_offer", "openrouter_free", {**steward.offer("openrouter_free"), "models": []})
    with pytest.raises(ProviderApprovalError, match="no longer"):
        steward.before_request("openrouter_free", "test:free", hashlib.sha256(b"key").hexdigest())


def test_approved_fallback_is_used_after_failure_and_tracks_provider():
    steward = make_steward(failover=True)
    approve(steward)
    approve(steward, "gemini", fallback=True)
    primary, secondary = RecordingProvider(error=True), RecordingProvider("gemini")
    managed = ManagedProvider(primary, "groq", steward, lambda _: secondary)
    assert managed.generate(ModelRequest(prompt="hello")).provider == "gemini"
    assert managed.name == "gemini" and secondary.calls == 1
    assert steward.memory.records("provider_health")


@pytest.mark.parametrize("partial,tools", [(True, False), (False, True)])
def test_failover_does_not_mix_partial_output_or_retry_tool_actions(partial, tools):
    steward = make_steward(failover=True)
    approve(steward)
    primary, local = RecordingProvider(error=True, emit=partial), RecordingProvider("ollama")
    managed = ManagedProvider(primary, "groq", steward, lambda _: local, local)
    request = ModelRequest(prompt="hello", tools=[ModelToolDefinition(name="tool", description="test")] if tools else [])
    with request_scope(RequestControl()), pytest.raises(RuntimeError):
        managed.generate(request)
    assert local.calls == 0


def test_optional_local_fallback_does_not_need_cloud_approval():
    steward = make_steward(failover=True)
    approve(steward)
    local = RecordingProvider("ollama")
    managed = ManagedProvider(RecordingProvider(error=True), "groq", steward, lambda _: local, local)
    assert managed.generate(ModelRequest(prompt="hello")).provider == "ollama"


def test_product_mode_ignores_environment_credentials_and_personal_plan():
    hub = IntelligenceHub(JarvisSettings(groq_api_key="developer-secret"), PersonalMemory())
    hub.steward.configure(enabled=True, auto_review=True, commercial=True, allow_failover=False, daily_limit=100)
    assert hub.api_key("groq") == ""
    for action in (lambda: hub.provider("chatgpt_plan"), lambda: hub.list_models("chatgpt_plan"),
                   lambda: hub.save_preferences("chatgpt_plan", "", True, "dark")):
        with pytest.raises(ProviderApprovalError):
            action()


def test_activation_checks_account_catalog_without_inference(monkeypatch):
    hub = IntelligenceHub(JarvisSettings(groq_api_key="key"), PersonalMemory())
    hub.steward = make_steward()
    hub.steward.approve_connection("groq", free_account_confirmed=True, terms_reviewed=True)
    monkeypatch.setattr(hub, "list_models", lambda _: [{"id": "test", "name": "Test"}])
    with pytest.raises(ProviderApprovalError):
        hub.activate_managed("groq", "absent")
    hub.activate_managed("groq", "test")
    assert hub.steward.approval("groq")["active"]


def test_failed_refresh_keeps_last_evidence_without_extending_approval():
    steward = make_steward()
    approve(steward)
    previous = steward.approval("groq")
    steward.transport = httpx.MockTransport(lambda _: httpx.Response(503))
    steward.review()
    assert steward.offer("groq")["error"]
    assert steward.require_connection("groq") == previous


def test_rate_limit_creates_cooldown_without_storing_raw_error():
    steward = make_steward()
    approve(steward)
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.com"))
    error = httpx.HTTPStatusError("sensitive error", request=response.request, response=response)
    steward.record_failure("groq", error)
    record = steward.memory.records("provider_health")[0]
    assert record["reason"] == "rate_limit" and "sensitive" not in str(record)
    with pytest.raises(ProviderApprovalError, match="cooling down"):
        steward.before_request("groq", "test", hashlib.sha256(b"key").hexdigest())


@pytest.mark.parametrize("limit,expected_calls", [(1, 1), (2, 2)])
def test_gemini_retries_count_towards_managed_daily_cap(limit, expected_calls, monkeypatch):
    from jarvis.models.gemini import GeminiProvider

    steward = make_steward(limit=limit)
    approve(steward, "gemini")
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(503)
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    delegate = GeminiProvider(provider_name="gemini", model="test", api_key="key",
                              base_url="https://example.test", transport=httpx.MockTransport(handle))
    managed = ManagedProvider(delegate, "gemini", steward, lambda _: pytest.fail("No provider switch"))
    with request_scope(RequestControl()), pytest.raises(ProviderApprovalError, match="allowance"):
        managed.generate(ModelRequest(prompt="Hello"))
    assert len(calls) == expected_calls
    assert not steward.memory.records("provider_health")
