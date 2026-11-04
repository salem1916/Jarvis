import httpx

from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_control import RequestControl, request_scope
from jarvis.models.base import ModelRequest
from jarvis.models.gemini import GeminiProvider
from jarvis.runtime.api_usage import ApiUsage


def test_usage_is_per_key_and_never_guesses_remaining_balance():
    memory = PersonalMemory()
    usage = ApiUsage(memory)
    usage.record("gemini", "secret-one", {"promptTokenCount": 12, "candidatesTokenCount": 3, "totalTokenCount": 18}, {})
    assert "total 18" in usage.report("gemini", "secret-one")
    assert "not reported yet" in usage.report("gemini", "other-key")
    assert "secret-one" not in str(memory.records("api_usage"))
    assert "not reported here" in usage.report("gemini", "secret-one")


def test_groq_rate_window_headers_are_not_total_credit_balance():
    usage = ApiUsage(PersonalMemory())
    usage.record("groq", "key", {"total_tokens": 3}, {"x-ratelimit-remaining-tokens": "997"})
    assert "rate-limit window: 997" in usage.report("groq", "key")


def test_gemini_stream_reports_usage_once_at_completion():
    calls = []
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text='data: {"usageMetadata":{"promptTokenCount":4,"candidatesTokenCount":1,"totalTokenCount":5},"candidates":[{"content":{"parts":[{"text":"Hi"}]},"finishReason":"STOP"}]}\n\n'))
    p = GeminiProvider(provider_name="gemini",model="test",api_key="fake",base_url="https://example.test",transport=transport)
    p.usage_callback = lambda usage, headers: calls.append(usage)
    with request_scope(RequestControl(on_delta=lambda _: None)):
        assert p.generate(ModelRequest(prompt="Hi")).text == "Hi"
    assert len(calls) == 1 and calls[0]["totalTokenCount"] == 5
