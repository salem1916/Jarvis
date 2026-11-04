"""Opt-in live voice -> Qt worker -> model -> real UI -> spoken-output check.

Uses only a generated fixture app and an isolated browser. It does not record
the user's microphone or send private screen content. Existing provider access
is used explicitly through --provider; ordinary pytest never runs this script.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.models.chatgpt_account import ChatGPTAccount
from jarvis.models.chatgpt_plan import ChatGPTPlanProvider
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.security.capabilities import Capability
from jarvis.security.credential_vault import CredentialVault
from jarvis.security.policy import PermissionDecision
from jarvis.tools.browser_mcp import BrowserMCPTool, PlaywrightMCP
from jarvis.tools.desktop_context import DesktopContext
from jarvis.tools.list_open_windows import ListOpenWindowsTool
from jarvis.tools.open_url import OpenUrlTool
from jarvis.tools.screen_observation import ScreenObservationTool
from jarvis.ui.pages.chat_page import ChatPage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["plan", "groq"], required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    workspace = root / "workspace" / ("acceptance-" + args.provider)
    workspace.mkdir(parents=True, exist_ok=True)
    ready = workspace / "fixture-ready.json"
    if ready.exists():
        ready.unlink()
    qt = QApplication.instance() or QApplication([])
    child_env = dict(os.environ)
    child_env.pop("QT_QPA_PLATFORM", None)
    fixture = subprocess.Popen([sys.executable, str(root / "scripts/acceptance_fixture.py"), "--ready-file", str(ready)],
                               env=child_env, creationflags=subprocess.CREATE_NO_WINDOW)
    app = build_application(JarvisSettings(workspace_dir=workspace))
    page = ChatPage(app, "You are Jarvis. Complete the user's actual request using real tools.")
    browser = BrowserMCPTool(PlaywrightMCP(headless=False))
    voice = page.voice_panel.controller

    def wait(predicate, limit=90):
        end = time.monotonic() + limit
        while time.monotonic() < end:
            qt.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        raise AssertionError("Timed out. " + page.activity_message.text() + " " + page.details_view.toPlainText()[-400:])

    try:
        wait(ready.exists, 10)
        handle = json.loads(ready.read_text(encoding="utf-8"))["handle"]
        window_tool = app.tool_service.registry.get("list_open_windows")
        assert isinstance(window_tool, ListOpenWindowsTool)
        catalog = window_tool.catalog
        actual = catalog.backend
        class ScopedBackend:
            def list_windows(self):
                return tuple(entry for entry in actual.list_windows() if entry.handle == handle)
            def focus(self, handle: int): return actual.focus(handle)
            def minimize(self, handle: int): return actual.minimize(handle)
            def maximize(self, handle: int): return actual.maximize(handle)
            def restore(self, handle: int): return actual.restore(handle)
        catalog.backend = ScopedBackend()
        # Allow actions only in this isolated test application; persisted user
        # permission modes are never changed.
        for capability in (Capability.INSPECT_UI, Capability.CLICK_UI, Capability.CONTROL_APPLICATION,
                           Capability.USE_BROWSER, Capability.OPEN_APPLICATION, Capability.TYPE_TEXT, Capability.KEYBOARD_ACTION):
            app.tool_service.executor.policy.set_decision(capability, PermissionDecision.ALLOW)
        state = JarvisSettings().state_dir
        vault = CredentialVault(state)
        if args.provider == "plan":
            provider = ChatGPTPlanProvider(ChatGPTAccount(vault), "gpt-6.1-sol")
        else:
            key = vault.get("api_keys").get("groq")
            if not key:
                raise RuntimeError("No Groq key is saved.")
            class CheckedGroq(OpenAICompatibleProvider):
                def generate(self, request):
                    try:
                        result = super().generate(request)
                        if request.json_output:
                            print("Fixture planner:", result.text[:1200], flush=True)
                        elif request.tools:
                            print("Fixture native calls:", [(call.name, call.arguments) for call in result.tool_calls], flush=True)
                        return result
                    except Exception as error:
                        response = getattr(error.__cause__, "response", None)
                        if response is not None and response.status_code == 400:
                            detail = response.json().get("error", {})
                            print("Groq fixture diagnostic:", detail.get("code"), str(detail.get("message", ""))[:400], flush=True)
                            print("Generated fixture data:", str(detail.get("failed_generation", ""))[:1600], flush=True)
                        raise
            provider = CheckedGroq(provider_name="groq", model="openai/gpt-oss-20b", base_url="https://api.groq.com/openai/v1", api_key=key, timeout=25)
        app.cloud_provider = provider
        app.screen_control_enabled = True
        screen = app.tool_service.registry.get("observe_screen")
        assert isinstance(screen, ScreenObservationTool)
        screen.enabled = True
        screen.follow_active = True
        fixture_handle = handle
        class FixtureContext(DesktopContext):
            @staticmethod
            def _usable(handle):
                # The user can keep working during a cloud request. Scope
                # automatic tracking to the generated app, never private apps.
                return handle == fixture_handle and DesktopContext._usable(handle)
        screen.context = FixtureContext()
        original_capture = screen.capture
        original_execute = screen.execute
        def scoped_observe(arguments):
            if arguments.get("scope") == "desktop" or not screen.resolve_window():
                raise PermissionError("Full-display capture is outside this generated-window acceptance test.")
            return original_execute(arguments)
        screen.execute = scoped_observe
        def scoped_capture(target):
            if target != handle:
                raise PermissionError("The active app moved outside the generated fixture. No private screen was captured.")
            return original_capture(target)
        screen.capture = scoped_capture
        def open_url(url):
            if url != "https://www.google.com/":
                raise ValueError("Only the explicit Google-open fixture is allowed in this acceptance check.")
            return bool(browser.execute({"action":"navigate", "url":url}).get("ok"))
        url_tool = app.tool_service.registry.get("open_url")
        assert isinstance(url_tool, OpenUrlTool)
        url_tool._opener = open_url
        # Collect actual generated output without sending commands or replies to
        # physical speakers. No physical microphone is opened by this check.
        voice._start_playback = lambda: None
        voice.enable(True)
        wait(lambda: voice.ready, 90)

        def speak_command(command):
            voice.interrupt()
            voice.say(command)
            wait(lambda: voice._synthesis_done and bool(voice._playback))
            pcm = bytes(voice._playback)
            voice.interrupt()
            before = page.chat_view.toPlainText()
            voice._send("transcribe", audio=base64.b64encode(pcm).decode(), rate=24000, channels=1, format="s16")
            wait(lambda: page.chat_view.toPlainText() != before)
            wait(lambda: page.worker_thread is None and page._reply is not None)
            wait(lambda: voice._synthesis_done and bool(voice._playback))
            reply = page._reply
            assert reply is not None
            print("Command:", command, "\nReply:", reply.message, "\nKind:", reply.kind, flush=True)
            assert reply.kind not in {"failed", "partial", "cancelled"}, reply.details
            return reply

        heard = speak_command("Can you hear me clearly?")
        assert "heard you" in heard.message.casefold()
        identity = speak_command("Who are you, and can you open apps for me?")
        assert "jarvis" in identity.details.casefold()
        assert "cannot open" not in identity.details.casefold() and "can't open" not in identity.details.casefold()
        opened = speak_command("Open Google.")
        assert "Opened Google" in opened.message
        catalog.backend.focus(handle)
        command = ("Click Show details in the Acceptance Test Window and read the reference on the screen."
                   if args.provider == "plan" else "Click Show summary in the Acceptance Test Window and read the status.")
        result = speak_command(command)
        expected = "LIME-27" if args.provider == "plan" else "READY"
        assert expected in result.details.upper(), result.details
        assert expected in result.spoken_text.upper(), "The spoken answer omitted the requested result: " + result.spoken_text
        assert voice.source is None
        # Confirm the generated final PCM really contains the result, rather
        # than merely checking that a speech buffer exists after progress.
        spoken_pcm = bytes(voice._playback)
        voice.interrupt()
        voice.transcript.disconnect(page._voice_prompt)
        spoken_transcripts = []
        voice.transcript.connect(spoken_transcripts.append)
        voice._send("transcribe", audio=base64.b64encode(spoken_pcm).decode(), rate=24000, channels=1, format="s16")
        wait(lambda:bool(spoken_transcripts))
        words = re.sub(r"[^a-z0-9]", "", spoken_transcripts[-1].casefold())
        if args.provider == "plan":
            # Whisper may spell the spoken homophone "lime" as "Lyme".
            assert any(word in words for word in ("lime", "lyme")) and ("27" in words or "twentyseven" in words), spoken_transcripts[-1]
        else:
            assert "ready" in words, spoken_transcripts[-1]
        print("Synthesized final reply recognized:", spoken_transcripts[-1], flush=True)
        print("PASS: live voice, local opening, actual model, real named-control click, observation and Kokoro output.", flush=True)
    finally:
        voice.stop_session()
        page._stop_request()
        wait(lambda: page.worker_thread is None, 40)
        process = voice.process
        voice.shutdown()
        if process is not None:
            process.waitForFinished(3000)
        browser.close()
        page.close()
        app.shutdown()
        fixture.terminate()
        fixture.wait(timeout=5)
        qt.processEvents()


if __name__ == "__main__":
    main()
