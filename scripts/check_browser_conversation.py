"""Real browser + application orchestration, using a local fixture and no cloud.

No personal tabs, microphone, speakers, or visible windows are opened.
"""
import argparse
import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from check_mcp_browser import Fixture, Planner

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings, load_settings
from jarvis.core.request_control import RequestControl, RetryBudget
from jarvis.models.base import ModelProvider
from jarvis.runtime.provider_steward import ManagedProvider
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.tools.browser_mcp import BrowserMCPTool, PlaywrightMCP


class SingleRequestProvider(ModelProvider):
    """Keep an explicitly requested live check to one provider and one request."""
    name = "groq"

    def __init__(self, delegate):
        self.delegate = delegate
        self.model = delegate.model
        self.calls = 0

    def generate(self, request):
        if self.calls:
            raise ValueError("The one-request live check stopped before sending another request.")
        self.calls += 1
        if isinstance(self.delegate, ManagedProvider):
            # Preserve authorization and usage accounting, without failover.
            return self.delegate._call(self.delegate.delegate, self.delegate.source, request)
        return self.delegate.generate(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-groq", action="store_true", help="Send one fixture-page reasoning request using the saved Groq connection.")
    options = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    client = PlaywrightMCP(headless=True, mode="isolated")
    replies = []
    live_app = None
    try:
        live_provider = None
        if options.live_groq:
            live_app = build_application(load_settings())
            hub = live_app.intelligence
            assert hub is not None
            live_provider = SingleRequestProvider(hub.provider("groq", hub.model_for("groq")))
        with tempfile.TemporaryDirectory(prefix="jarvis-flow-") as directory:
            root = Path(directory)
            app = build_application(JarvisSettings(workspace_dir=root, state_dir=root / "state"))
            try:
                browser = app.tool_service.registry.get("browser_mcp")
                assert isinstance(browser, BrowserMCPTool)
                browser.client = client
                planner = live_provider or Planner()
                app.cloud_provider = app.local_worker_provider = planner
                for cap in (Capability.USE_BROWSER, Capability.CLICK_UI, Capability.TYPE_TEXT, Capability.KEYBOARD_ACTION):
                    app.tool_service.executor.policy.set_decision(cap, PermissionDecision.ALLOW)
                # Localhost is allowed only inside this test process.
                with patch("jarvis.tools.browser_mcp.public_url", side_effect=lambda url: url == base or url.startswith(base + "/")):
                    reply = app.interact("Open " + base)
                    assert reply.kind == "action", reply.details
                    assert app.interaction.focus_url == browser.last["url"] == base + "/"
                    replies.append(reply.message)
                    if live_provider:
                        reply = app.interact("browser: Read the current page title. Answer with the title and finish; don't change the page.",
                                             request_control=RequestControl(retry_budget=RetryBudget(limit=0)))
                        assert reply.kind == "action" and "Jarvis local MCP check" in reply.details, reply.details
                    else:
                        reply = app.interact("browser: Search this page for Java tutorials and tell me the result.")
                        assert reply.kind == "action" and "Java tutorials" in reply.message, reply.details
                    replies.append(reply.message)
                    calls = planner.calls
                    reply = app.interact("Can you open " + base + "/details in it?", request_control=RequestControl(input_source="voice"))
                    assert reply.kind == "action" and browser.last["url"] == base + "/details", reply.details
                    replies.append(reply.message)
                    reply = app.interact("No, wait, go back", request_control=RequestControl(input_source="voice"))
                    assert reply.kind == "action" and browser.last["url"] == base + "/", reply.details
                    assert planner.calls == calls
                    replies.append(reply.message)
                    tab_result = browser.execute({"action":"tabs"})
                    assert isinstance(tab_result, dict)
                    tabs = tab_result["tabs"]
                    assert "- 0:" in tabs and "- 1:" not in tabs
            finally:
                app.shutdown()
        assert client.thread is None
        print(json.dumps({"application_flow":True, "same_tab":True, "back_without_ai":True,
            "simulated_voice_instructions":True, "backend_closed":True, "cloud_calls":live_provider.calls if live_provider else 0,
            "microphone_opened":False, "speaker_opened":False, "replies":replies}))
    finally:
        client.close()
        if live_app is not None:
            live_app.shutdown()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
