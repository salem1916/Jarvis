import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import pytest

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.request_control import (
    RequestCancelledError,
    RequestControl,
    request_scope,
)
from jarvis.models.base import ModelProvider, ModelResponse
from jarvis.models.cancellable_http import CancellableClient
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.tools.executor import PermissionDeniedError
from jarvis.tools.web_research import WebResearchTool, public_url, research_query


@pytest.mark.parametrize("text", ["open google and see the stock market", "research current processor benchmarks", "check the stock market"])
def test_research_request_is_distinct_from_opening_a_search_url(text):
    assert research_query(text)
    assert research_query("search for Java tutorials") is None


@pytest.mark.parametrize("url", ["http://example.com", "https://127.0.0.1", "https://localhost", "https://user:pass@example.com", "file:///C:/secret"])
def test_public_web_reader_rejects_private_or_credential_urls(url):
    assert not public_url(url)


def test_research_cancellation_terminates_pending_coroutine():
    tool = WebResearchTool(headless=True)
    entered, stopped = Event(), Event()
    async def wait(query):
        entered.set()
        try:
            await asyncio.sleep(60)
        finally:
            stopped.set()
    tool._research = wait
    control = RequestControl()
    def run():
        with request_scope(control):
            tool.execute({"query": "test"})
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run)
            assert entered.wait(2)
            started = time.monotonic()
            control.cancelled.set()
            with pytest.raises(RequestCancelledError):
                future.result(timeout=1)
            assert time.monotonic() - started < 1
            assert stopped.wait(1)
    finally:
        tool.close()


@pytest.mark.parametrize("stream", [False, True])
def test_stop_cancels_real_http_wait_instead_of_waiting_for_timeout(stream):
    entered, release = Event(), Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if stream:
                self.send_response(200)
                self.end_headers()
                self.wfile.flush()
            entered.set()
            release.wait(4)
        def log_message(self, format, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    control = RequestControl()
    def run():
        with request_scope(control), CancellableClient(timeout=30) as client:
            url = f"http://127.0.0.1:{server.server_port}"
            if stream:
                with client.stream("POST", url) as response:
                    list(response.iter_lines())
            else:
                client.post(url)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run)
            assert entered.wait(3)
            control.cancelled.set()
            with pytest.raises(RequestCancelledError):
                future.result(timeout=2)
    finally:
        release.set()
        server.shutdown()
        server.server_close()


def test_full_research_passes_only_observed_sources_and_streams_citations(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path, gemini_api_key="fake"))
    hub = app.intelligence
    assert hub is not None
    hub.save_preferences("gemini", "test-model", True, "dark")
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    sources = [{"title": "Observed page", "url": "https://example.com/source", "retrieved_at": "2026-10-31T12:00:00Z", "text": "Observed evidence"}]
    class Model(ModelProvider):
        name = "test"
        def generate(self, request):
            if request.system_prompt and '"queries"' in request.system_prompt:
                return ModelResponse(text='{"queries":["a topic"]}', provider="test", model="test")
            if request.system_prompt and '"relevant"' in request.system_prompt:
                return ModelResponse(text='{"relevant":[1],"sufficient":true}', provider="test", model="test")
            assert "Observed evidence" in str(request)
            assert "Never equate" in str(request) or "never equate" in str(request)
            assert not request.tools
            return ModelResponse(text="Summary [1]", provider="test", model="test")
    deltas = []
    tool = app.tool_service.registry.get("research_web")
    try:
        with patch.object(tool, "execute", return_value={"ok": True, "sources": sources}), patch.object(hub, "provider", return_value=Model()):
            answer = app.ask_with_tools("research a topic", request_control=RequestControl(on_delta=deltas.append))
        assert "https://example.com/source" in answer and "https://example.com/source" in "".join(deltas)
        assert "Summary [1]" in str(app.conversation.snapshot())
    finally:
        app.shutdown()


def test_denied_research_does_not_start_browser(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.DENY)
    tool = app.tool_service.registry.get("research_web")
    try:
        with patch.object(tool, "execute", side_effect=AssertionError("Browser started")), pytest.raises(PermissionDeniedError):
            app.ask_with_tools("research a topic")
    finally:
        app.shutdown()


def test_stop_drains_delayed_async_reader_before_closing_stream():
    import httpx

    entered, unwound, closed = Event(), Event(), Event()
    class DelayedReader(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            try:
                await asyncio.Event().wait()
                yield b"unused"
            finally:
                # Cleanup may itself need an event-loop turn after cancellation.
                await asyncio.sleep(0.05)
                unwound.set()
        async def aclose(self):
            assert unwound.is_set(), "Response closed before its active reader unwound"
            closed.set()
    control = RequestControl()
    def run():
        transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=DelayedReader()))
        with (
            request_scope(control),
            CancellableClient(transport=transport, timeout=30) as client,
            client.stream("POST", "https://example.test") as response,
        ):
            list(response.iter_lines())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            assert entered.wait(3)
        finally:
            control.cancelled.set()
        with pytest.raises(RequestCancelledError):
            future.result(timeout=2)
    assert unwound.is_set() and closed.is_set()
