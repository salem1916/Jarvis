import json
import time
from pathlib import Path
from threading import Event
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from jarvis.agents.hermes_bridge import JarvisHermesBridge
from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.request_control import (
    RequestCancelledError,
    RequestControl,
    request_scope,
)
from jarvis.models.base import ModelMessage, ModelRequest, ModelResponse
from jarvis.models.chatgpt_account import ISSUER, PLAN_SCOPE, RESOURCE, ChatGPTAccount
from jarvis.models.chatgpt_plan import ChatGPTPlanProvider
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.runtime.profile import RuntimeMode
from jarvis.security.credential_vault import CredentialVault


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def account_fixture(signing_key, *, scopes=PLAN_SCOPE, identity_changes=None):
    captured = []
    vault = CredentialVault()
    attempt = {}
    key = RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    key["kid"] = "test-key"

    def handle(request):
        captured.append(request)
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json={"keys": [key]})
        if request.url.path.endswith("/token"):
            form = parse_qs(request.content.decode())
            if form.get("grant_type") == ["refresh_token"]:
                assert form["client_id"] == ["oaiapp_test"]
                assert form["resource"] == [RESOURCE]
                assert "scope" not in form
                return httpx.Response(200, json={"access_token": "renewed-access", "refresh_token": "rotated-refresh", "expires_in": 3600})
            assert form["code_verifier"] == [attempt["verifier"]]
            assert form["redirect_uri"] == [attempt["redirect_uri"]]
            assert form["client_id"] == ["oaiapp_test"]
            claims = {"sub": "account-1", "email": "test@example.invalid", "iss": ISSUER,
                      "aud": "oaiapp_test", "iat": time.time(), "exp": time.time() + 3600, "nonce": attempt["nonce"]}
            claims.update(identity_changes or {})
            token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})
            return httpx.Response(200, json={"access_token": "test-access", "refresh_token": "test-refresh",
                                           "id_token": token, "scope": scopes, "expires_in": 3600})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"models": [
                {"slug": "visible-model", "display_name": "Available model", "visibility": "list"},
                {"slug": "hidden-model", "visibility": "hide"},
            ]})
        return httpx.Response(500)

    account = ChatGPTAccount(vault, httpx.MockTransport(handle))
    attempt.update(account.begin("http://127.0.0.1:9876/auth/callback"))
    return account, attempt, captured


def callback(attempt):
    return {"state": [attempt["state"]], "client_id": ["oaiapp_test"], "code": ["test-code"]}


def test_oauth_dynamic_registration_verifies_identity_and_discovers_models(signing_key):
    account, attempt, captured = account_fixture(signing_key)
    query = parse_qs(urlsplit(attempt["url"]).query)
    assert query["client_id"] == ["dynamic_agent_client"]
    assert query["agent_name_hint"] == ["JARVIS"]
    assert query["code_challenge_method"] == ["S256"]
    assert "credits" not in query
    assert query["ext_agent_host_id"][0].startswith("urn:uuid:")
    account.complete(attempt, callback(attempt))
    assert account.session()["sharing"]
    assert account.access_token() == "test-access"
    assert account.list_models() == [{"id": "visible-model", "name": "Available model"}]
    returning = account.begin("http://127.0.0.1:9877/auth/callback")
    params = parse_qs(urlsplit(returning["url"]).query)
    assert params["client_id"] == ["oaiapp_test"]
    assert "agent_name_hint" not in params
    assert params["ext_agent_host_id"] == query["ext_agent_host_id"]
    assert all("test-access" not in str(p) for p in account.profiles())
    assert len(captured) == 3


@pytest.mark.parametrize("changes", [
    {"nonce": "wrong"}, {"aud": "wrong-client"}, {"iss": "https://attacker.invalid"}, {"exp": 1},
])
def test_oauth_rejects_invalid_signed_identity(signing_key, changes):
    account, attempt, _ = account_fixture(signing_key, identity_changes=changes)
    with pytest.raises(ValueError, match="verification"):
        account.complete(attempt, callback(attempt))
    assert not account.session()["connected"]


def test_oauth_state_failure_happens_before_network_and_attempt_cannot_be_replayed(signing_key):
    account, attempt, captured = account_fixture(signing_key)
    query = callback(attempt)
    query["state"] = ["wrong-state"]
    with pytest.raises(ValueError, match="state"):
        account.complete(attempt, query)
    assert not captured
    with pytest.raises(ValueError, match="expired"):
        account.complete(attempt, callback(attempt))


def test_identity_signin_does_not_grant_plan_access(signing_key):
    account, attempt, _ = account_fixture(signing_key, scopes="openid email")
    account.complete(attempt, callback(attempt))
    assert account.session()["connected"]
    assert not account.session()["sharing"]
    with pytest.raises(ValueError, match="allow plan"):
        account.access_token()


def test_refresh_rotates_token_and_retains_registration(signing_key):
    account, attempt, captured = account_fixture(signing_key)
    account.complete(attempt, callback(attempt))
    saved = account.vault.get("chatgpt")
    saved["profiles"]["oaiapp_test"]["expires_at"] = 0
    account.vault.set("chatgpt", saved)
    assert account.access_token() == "renewed-access"
    profile = account.vault.get("chatgpt")["profiles"]["oaiapp_test"]
    assert profile["refresh_token"] == "rotated-refresh"
    assert PLAN_SCOPE in profile["scopes"]
    assert account.access_token() == "renewed-access"
    assert sum(r.url.path.endswith("/token") for r in captured) == 2


def test_signout_clears_local_tokens_if_remote_revocation_is_unconfirmed(signing_key):
    account, attempt, _ = account_fixture(signing_key)
    account.complete(attempt, callback(attempt))
    assert not account.sign_out()  # Mock revocation returns 500.
    assert not account.session()["connected"]
    saved = account.vault.get("chatgpt")
    assert saved["profiles"]["oaiapp_test"]["client_id"] == "oaiapp_test"
    assert "refresh_token" not in saved["profiles"]["oaiapp_test"]


def test_encrypted_windows_vault_roundtrip_does_not_store_plaintext(tmp_path: Path):
    vault = CredentialVault(tmp_path)
    vault.set("api_keys", {"groq": "not-a-real-secret-for-test"})
    assert vault.path is not None
    assert b"not-a-real-secret" not in vault.path.read_bytes()
    assert CredentialVault(tmp_path).get("api_keys")["groq"] == "not-a-real-secret-for-test"


def plan_provider(events, inspect=None):
    def handle(request):
        if inspect:
            inspect(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content="".join("data: " + json.dumps(e) + "\n\n" for e in events).encode())
    account = ChatGPTAccount(CredentialVault(), httpx.MockTransport(handle))
    with patch.object(account, "access_token", return_value="test-access"):
        yield ChatGPTPlanProvider(account, "account-model")


def test_chatgpt_plan_uses_public_streaming_responses_contract():
    events = [{"type": "response.output_text.delta", "delta": "Hello"}, {"type": "response.completed"}]
    deltas = []

    def inspect(request):
        assert str(request.url) == RESOURCE + "/responses"
        data = json.loads(request.content)
        assert data["store"] is False and data["stream"] is True
        assert data["instructions"] == "Personal context"
        assert all(m["role"] != "system" for m in data["input"])
        assert "max_output_tokens" not in data

    result = None
    for provider in plan_provider(events, inspect):
        with request_scope(RequestControl(on_delta=deltas.append)):
            result = provider.generate(ModelRequest(prompt="Hi", messages=[ModelMessage(role="system", content="Personal context")]))
    assert result is not None and result.text == "Hello"
    assert deltas == ["Hello"]


@pytest.mark.parametrize("terminal", ["response.failed", "response.incomplete", "interrupted"])
def test_plan_partial_text_is_not_treated_as_completion(terminal):
    events = [{"type": "response.output_text.delta", "delta": "Partial"}]
    if terminal != "interrupted":
        events.append({"type": terminal})
    for provider in plan_provider(events):
        with pytest.raises(ValueError):
            provider.generate(ModelRequest(prompt="Hi"))


def test_stopping_stream_does_not_commit_partial_chat_or_memory(tmp_path: Path):
    stop = Event()
    chunks = [
        {"choices": [{"delta": {"content": "Partial"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": " more"}, "finish_reason": "stop"}]},
    ]
    body = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=body.encode()))
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.cloud_provider = OpenAICompatibleProvider(provider_name="test", model="test", base_url="https://test.invalid",
                                                  api_key="test", transport=transport)
    control = RequestControl(on_delta=lambda text: stop.set(), cancelled=stop)
    with pytest.raises(RequestCancelledError):
        app.ask_with_tools("Explain SQL", request_control=control)
    assert len(app.conversation) == 0
    assert not app.personal_memory.recent_turns()
    app.shutdown()


def test_cancelled_hermes_bridge_rejects_actions_even_from_another_thread(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    control = RequestControl()
    with request_scope(control):
        bridge = JarvisHermesBridge(app.tool_service)
    control.cancelled.set()
    with pytest.raises(RequestCancelledError):
        bridge.execute("open_application", {"application": "notepad"})
    app.shutdown()


def test_free_only_source_rejects_paid_models_and_never_falls_back(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path, openai_api_key="test-key"))
    hub = app.intelligence
    assert hub is not None
    with pytest.raises(ValueError, match="Free-only"):
        hub.save_preferences("openrouter_free", "paid/model", True, "dark")
    hub.save_preferences("groq", "openai/gpt-oss-20b", True, "dark")
    with patch.object(app.cloud_provider, "generate", side_effect=AssertionError("Paid fallback called")), pytest.raises(ValueError, match="Connect Groq"):
        app.ask_with_tools("Explain SQL")
    assert not app.personal_memory.recent_turns()
    app.shutdown()


def test_internal_file_generation_obeys_local_only_mode(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.set_runtime_mode(RuntimeMode.LOCAL)
    generated = ModelResponse(text="Local file content", provider="ollama", model="test")
    with (patch.object(app.local_worker_provider, "generate", return_value=generated),
          patch.object(app.hermes_cloud_chat_agent_engine, "run", side_effect=AssertionError("Cloud called"))):
        assert app._generate_fast_write_content("a summary") == "Local file content"
    app.shutdown()


def test_worker_models_remain_assigned_when_main_connection_changes(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    hub = app.intelligence
    assert hub is not None
    hub.save_preferences("chatgpt_plan", "account-model", True, "dark")
    hub.save_preferences("groq", "openai/gpt-oss-20b", True, "dark")
    provider = hub.provider("chatgpt_plan")
    assert isinstance(provider, ChatGPTPlanProvider)
    assert provider.model == "account-model"
    app.shutdown()
