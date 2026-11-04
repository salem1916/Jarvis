import json

import httpx
import pytest

from jarvis.core.config import JarvisSettings
from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_control import RequestControl, request_scope
from jarvis.models.base import ModelMessage, ModelRequest, ModelToolDefinition
from jarvis.models.connection_errors import ProviderConnectionError
from jarvis.models.gemini import GeminiProvider
from jarvis.runtime.intelligence import IntelligenceHub


def provider(handler, model="gemini-3.8-flash", timeout=60):
    return GeminiProvider(provider_name="gemini", model=model, timeout=timeout,
                          base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                          api_key="fake-test-key", transport=httpx.MockTransport(handler))


def test_native_chat_maps_history_system_instruction_and_low_thinking():
    def handle(request):
        assert request.url.path.endswith("/gemini-3.8-flash:generateContent")
        assert request.headers["x-goog-api-key"] == "fake-test-key"
        assert "authorization" not in request.headers and "key=" not in str(request.url)
        payload = json.loads(request.content)
        assert payload["systemInstruction"]["parts"][0]["text"] == "Be concise"
        assert payload["contents"][1]["role"] == "model"
        assert payload["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "LOW"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Hello"}]}, "finishReason": "STOP"}]})
    request = ModelRequest(prompt="Hi", messages=[ModelMessage(role="system", content="Be concise"),
                           ModelMessage(role="user", content="Earlier"), ModelMessage(role="assistant", content="Earlier reply"),
                           ModelMessage(role="user", content="Hi")])
    assert provider(handle).generate(request).text == "Hello"


def test_stream_uses_native_sse_and_configured_read_timeout():
    def handle(request):
        assert request.url.path.endswith(":streamGenerateContent")
        assert request.url.params["alt"] == "sse"
        assert request.extensions["timeout"]["read"] == 75
        return httpx.Response(200, text='data: {"candidates":[{"content":{"parts":[{"text":"Hi "}]}}]}\n\n'
                              'data: {"candidates":[{"content":{"parts":[{"text":"there"}]},"finishReason":"STOP"}]}\n\n')
    deltas = []
    with request_scope(RequestControl(on_delta=deltas.append)):
        response = provider(handle, timeout=75).generate(ModelRequest(prompt="Hi"))
    assert response.text == "Hi there" and deltas == ["Hi ", "there"]


@pytest.mark.parametrize("stream", [False, True])
def test_overload_is_reported_after_bounded_retries_without_leaking_key(stream, monkeypatch):
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "fake-test-key"}})
    with (request_scope(RequestControl(on_delta=(lambda _: None) if stream else None)),
          pytest.raises(ProviderConnectionError, match="temporarily busy") as error):
        provider(handle).generate(ModelRequest(prompt="Hi"))
    assert len(calls) == 3 and "fake-test-key" not in str(error.value)
    assert error.value.status_code == 503


def test_tool_requests_stay_on_existing_compatibility_adapter():
    def handle(request):
        assert request.url.path.endswith("/openai/chat/completions")
        assert json.loads(request.content)["tools"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "Done"}}]})
    assert provider(handle).generate(ModelRequest(prompt="Hi", tools=[ModelToolDefinition(name="test", description="Test")])).text == "Done"


def test_incomplete_native_stream_is_not_accepted_as_complete():
    with (request_scope(RequestControl(on_delta=lambda _: None)), pytest.raises(ValueError, match="complete text reply")):
        provider(lambda _: httpx.Response(200, text='data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}\n\n')).generate(ModelRequest(prompt="Hi"))


def test_thought_parts_are_not_displayed():
    data = {"candidates": [{"content": {"parts": [{"thought": True, "text": "private"}, {"text": "answer"}]}, "finishReason": "STOP"}]}
    assert provider(lambda _: httpx.Response(200, json=data)).generate(ModelRequest(prompt="Hi")).text == "answer"


def test_hub_selects_native_gemini_and_honors_concise_setting():
    hub = IntelligenceHub(JarvisSettings(gemini_api_key="fake-test-key"), PersonalMemory())
    hub.save_preferences("gemini", "gemini-3.1-flash-lite", False, "dark")
    p = hub.provider()
    assert isinstance(p, GeminiProvider) and not p.fast_replies
    assert "generationConfig" not in p._native_payload(ModelRequest(prompt="Hi"))


def test_native_stream_returns_at_stop_without_waiting_for_idle_connection():
    class OpenConnection(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]},"finishReason":"STOP"}]}\n\n'
            raise httpx.ReadTimeout("The connection stayed open after completion")
    def handle(request):
        return httpx.Response(200, stream=OpenConnection())
    with request_scope(RequestControl(on_delta=lambda _: None)):
        assert provider(handle).generate(ModelRequest(prompt="hey")).text == "Hello"


def test_new_gemini_connection_defaults_to_flash_lite():
    hub = IntelligenceHub(JarvisSettings(gemini_api_key="fake-test-key"), PersonalMemory())
    assert hub.model_for("gemini") == "gemini-3.1-flash-lite"


@pytest.mark.parametrize("signatures", [("opaque-first", "opaque-second"), ("opaque-first", None)])
def test_gemini_preserves_per_call_signatures_across_tool_results(signatures):
    from jarvis.models.openai_compatible import OpenAICompatibleProvider

    requests = []
    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            calls = []
            for index, signature in enumerate(signatures):
                call = {"id": f"call-{index}", "type": "function", "function": {"name": "probe", "arguments": "{}"}}
                if signature:
                    call["extra_content"] = {"google": {"thought_signature": signature}}
                calls.append(call)
            return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": calls}}]})
        sent = payload["messages"][1]["tool_calls"]
        for original, signature in zip(sent, signatures, strict=True):
            if signature:
                assert original["extra_content"] == {"google": {"thought_signature": signature}}
            else:
                assert "extra_content" not in original
        assert [m["tool_call_id"] for m in payload["messages"][2:]] == ["call-0", "call-1"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "Both results received."}}]})
    p = provider(handle)
    tools = [ModelToolDefinition(name="probe", description="Protocol test", parameters={"type":"object","properties":{}})]
    first = p.generate(ModelRequest(prompt="Use probe", tools=tools))
    # This round-trip also verifies that conversation copying retains opaque state.
    assistant = ModelMessage.model_validate(ModelMessage(role="assistant", tool_calls=first.tool_calls).model_dump())
    generic = OpenAICompatibleProvider._convert_message(assistant)
    generic_calls = generic["tool_calls"]
    assert isinstance(generic_calls, list)
    assert all("extra_content" not in call for call in generic_calls)
    assert signatures[0] not in repr(assistant)
    messages = [ModelMessage(role="user", content="Use probe"), assistant]
    messages.extend(ModelMessage(role="tool", content='{"ok":true}', tool_call_id=call.call_id) for call in first.tool_calls)
    assert p.generate(ModelRequest(prompt="Use probe", tools=tools, messages=messages)).text == "Both results received."
    assert len(requests) == 2
