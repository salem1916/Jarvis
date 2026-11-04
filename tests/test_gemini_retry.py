from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest

from jarvis.agents.browser_workflow import run_browser
from jarvis.agents.research import quiet_inference
from jarvis.core.request_control import (
    RequestCancelledError,
    RequestControl,
    request_scope,
)
from jarvis.models.base import ModelRequest, ModelToolDefinition
from jarvis.models.connection_errors import ProviderConnectionError, retry_after_seconds
from jarvis.models.gemini import GeminiProvider


def gemini(handler):
    return GeminiProvider(provider_name="gemini", model="gemini-3.1-flash-lite", api_key="test-secret",
                          base_url="https://generativelanguage.googleapis.com/v1beta/openai", transport=httpx.MockTransport(handler))


def reply(text):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


@pytest.mark.parametrize("status", [502, 503, 504])
@pytest.mark.parametrize("stream", [False, True])
def test_transient_failure_recovers_without_duplicate_text(status, stream, monkeypatch):
    calls, delays, deltas, progress = [], [], [], []
    def handle(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(status, json={"error": "test-secret"})
        if stream:
            return httpx.Response(200, text='data: {"candidates":[{"content":{"parts":[{"text":"Recovered"}]},"finishReason":"STOP"}]}\n\n')
        return reply("Recovered")
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", delays.append)
    with request_scope(RequestControl(on_delta=deltas.append if stream else None, on_status=progress.append)):
        answer = gemini(handle).generate(ModelRequest(prompt="Hello"))
    assert answer.text == "Recovered" and len(calls) == 3
    assert deltas == (["Recovered"] if stream else [])
    assert 1 <= delays[0] <= 1.2 and 2 <= delays[1] <= 2.2
    assert any("1/2" in text for text in progress) and any("2/2" in text for text in progress)
    assert all("test-secret" not in text for text in progress)
    assert len({str(request.url) for request in calls}) == 1
    assert len({request.content for request in calls}) == 1


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 408, 429, 500])
def test_other_http_errors_are_not_retried(status, monkeypatch):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status)
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: pytest.fail("Unexpected retry"))
    with pytest.raises(ProviderConnectionError) as error:
        gemini(handle).generate(ModelRequest(prompt="Hello"))
    assert len(calls) == 1 and error.value.status_code == status


def test_retry_after_is_honored_without_waiting_indefinitely(monkeypatch):
    delays, calls = [], []
    def handle(request):
        calls.append(request)
        return httpx.Response(503, headers={"Retry-After": "3" if len(calls) == 1 else "90"})
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", delays.append)
    with pytest.raises(ProviderConnectionError):
        gemini(handle).generate(ModelRequest(prompt="Hello"))
    assert delays == [3] and len(calls) == 2


@pytest.mark.parametrize("value,expected", [("2", 2), ("-3", 0), ("NaN", None), ("inf", None), ("invalid", None)])
def test_retry_after_rejects_unusable_headers(value, expected):
    assert retry_after_seconds(value) == expected


def test_retry_budget_is_shared_by_internal_planning_calls(monkeypatch):
    calls = []
    def handle(request):
        calls.append(request)
        return reply("First response") if len(calls) == 3 else httpx.Response(503)
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    provider = gemini(handle)
    with request_scope(RequestControl()):
        with quiet_inference():
            assert provider.generate(ModelRequest(prompt="First step")).text == "First response"
        with quiet_inference(), pytest.raises(ProviderConnectionError):
            provider.generate(ModelRequest(prompt="Next step"))
    assert len(calls) == 4


def test_stop_interrupts_retry_wait_and_does_not_send_again():
    entered = Event()
    calls = []
    control = RequestControl(on_status=lambda _: entered.set())
    def handle(request):
        calls.append(request)
        return httpx.Response(503)
    def run():
        with request_scope(control):
            return gemini(handle).generate(ModelRequest(prompt="Hello"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            assert entered.wait(2)
        finally:
            control.cancelled.set()
        with pytest.raises(RequestCancelledError):
            future.result(timeout=1)
    assert len(calls) == 1


def test_compatibility_tool_requests_retry_only_the_api_request(monkeypatch):
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.path.endswith("/openai/chat/completions")
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"choices":[{"message":{"content":"Ready"}}]})
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    answer = gemini(handle).generate(ModelRequest(prompt="Use the test tool", tools=[ModelToolDefinition(name="test", description="Test")]))
    assert answer.text == "Ready" and len(calls) == 2


@pytest.mark.parametrize("recover", [False, True])
def test_browser_retries_without_reopening_and_reports_partial_completion(recover, monkeypatch):
    requests, actions, progress = [], [], []
    def handle(request):
        requests.append(request)
        if recover and len(requests) == 3:
            return reply('{"action":"finish","answer":"Information read."}')
        return httpx.Response(503)
    def execute(arguments):
        actions.append(arguments)
        return {"ok": True, "url": "https://example.com/", "snapshot": "Observed page", "links": []}
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    with request_scope(RequestControl(on_status=progress.append)):
        answer = run_browser(gemini(handle), execute, "Open https://example.com and find information")
    assert len(actions) == 1 and len(requests) == 3
    assert "https://example.com/" in answer
    if recover:
        assert "Information read." in answer
    else:
        assert "Task partly completed" in answer and "Still needed" in answer and "HTTP 503" in answer
    assert any("Page read:" in text for text in progress)


def test_outage_before_navigation_never_claims_a_page_was_opened(monkeypatch):
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    actions = []
    def observe(arguments):
        actions.append(arguments)
        assert arguments == {"action":"snapshot"}
        return {"url":"", "snapshot":"No page is open", "links":[]}
    answer = run_browser(gemini(lambda _: httpx.Response(503)), observe, "Find contact information")
    assert actions == [{"action":"snapshot"}]
    assert "No page was observed" in answer and "Task partly completed" not in answer


def test_stopped_browser_request_includes_completed_page(monkeypatch):
    control = RequestControl()
    actions = []
    def execute(arguments):
        actions.append(arguments)
        return {"url":"https://example.com/", "snapshot":"Observed", "links":[]}
    def stop_wait(_):
        control.cancelled.set()
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", stop_wait)
    with request_scope(control), pytest.raises(RequestCancelledError) as error:
        run_browser(gemini(lambda _: httpx.Response(503)), execute, "Open https://example.com and read information")
    assert "https://example.com/" in str(error.value) and "incomplete" in str(error.value)
    assert len(actions) == 1


def test_failure_at_later_step_preserves_all_completed_pages(monkeypatch):
    calls, actions = [], []
    def handle(request):
        calls.append(request)
        if len(calls) == 2:
            return reply('{"action":"follow_link","link_index":1}')
        return httpx.Response(503)
    def execute(arguments):
        actions.append(arguments)
        url = "https://example.com/" if len(actions) == 1 else "https://example.com/contact"
        return {"url": url, "snapshot": "Observed", "links": [{"label":"Contact","url":"https://example.com/contact"}]}
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    with request_scope(RequestControl()):
        answer = run_browser(gemini(handle), execute, "Open https://example.com and read contact information")
    assert len(calls) == 4 and len(actions) == 2
    assert "Task partly completed" in answer and "https://example.com/contact" in answer
    assert actions[1] == {"action":"follow_link","link_index":1}


def test_stream_failure_after_partial_output_is_not_restarted(monkeypatch):
    calls, deltas = [], []
    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"candidates":[{"content":{"parts":[{"text":"Partial"}]}}]}\n\n'
            raise httpx.ReadError("Connection lost")
    def handle(request):
        calls.append(request)
        return httpx.Response(200, stream=BrokenStream())
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: pytest.fail("Partial output must not be restarted"))
    with request_scope(RequestControl(on_delta=deltas.append)), pytest.raises(ProviderConnectionError):
        gemini(handle).generate(ModelRequest(prompt="Hello"))
    assert deltas == ["Partial"] and len(calls) == 1
