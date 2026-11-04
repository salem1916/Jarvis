"""Local native-window check with an isolated browser and a loopback test page.

No cloud models, personal browser profile, microphone, or screen capture.
"""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import win32gui
from playwright.sync_api import sync_playwright
from PySide6.QtWidgets import QApplication

from jarvis.core.config import JarvisSettings
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.tools.screen_observation import ScreenObservationTool
from jarvis.ui.desktop import JarvisWindow


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<title>Jarvis isolated tab check</title><h1>Local browser navigation fixture</h1>"
        self.send_response(200);self.send_header("Content-Type","text/html");self.end_headers();self.wfile.write(body)

    def log_message(self,format,*args):
        pass


def main():
    parser = argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    output = parser.parse_args().output;output.mkdir(parents=True,exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    qt = QApplication.instance() or QApplication([])
    with patch("jarvis.ui.desktop.load_settings",return_value=JarvisSettings(workspace_dir=root/"workspace/interface-check")):
        window = JarvisWindow()
    app = window.jarvis
    server = ThreadingHTTPServer(("127.0.0.1",0),Fixture)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        window.resize(900,600);window.show();qt.processEvents()
        for index, name in ((0,"Assistant"),(1,"Tasks"),(2,"Permissions"),(3,"Settings"),(4,"Memory"),(5,"Logs"),(6,"API"),(7,"Updates")):
            window._navigate_to(index);qt.processEvents()
            assert window.grab().save(str(output/f"Jarvis-section-{name}.png"))
        window._navigate_to(0)
        window.chat_page.controls_button.click();qt.processEvents()
        assert window.chat_page.controls_dialog.isVisible()
        window.chat_page.controls_dialog.hide()
        companion = window.chat_page.companion
        assert companion is not None
        window.showMinimized();qt.processEvents();assert companion.isVisible()
        companion.open_button.click();qt.processEvents();assert not window.isMinimized()
        with sync_playwright() as driver:
            executable = next((root/".browsers").glob("chromium-*/chrome-win64/chrome.exe"))
            browser = driver.chromium.launch(executable_path=str(executable),headless=False)
            try:
                context = browser.new_context();page = context.new_page()
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(base);page.bring_to_front()
                handles = []
                def find_fixture(handle,_):
                    if win32gui.IsWindowVisible(handle) and "Jarvis isolated tab check" in win32gui.GetWindowText(handle):
                        handles.append(handle)
                    return True
                win32gui.EnumWindows(find_fixture,None)
                assert len(handles) == 1,"Expected one isolated browser fixture"
                screen = app.tool_service.registry.get("observe_screen")
                assert isinstance(screen,ScreenObservationTool)
                for capability in (Capability.USE_BROWSER,Capability.KEYBOARD_ACTION,Capability.TYPE_TEXT):
                    app.tool_service.executor.policy.set_decision(capability,PermissionDecision.ALLOW)
                with patch.object(screen.context,"current_window",return_value=handles[0]), \
                     patch.object(screen,"capture",side_effect=AssertionError("No screen image should be needed")), \
                     patch.object(app,"ask_with_tools",side_effect=AssertionError("No AI should be needed")):
                    reply = app.interact(f"Can you open {base}/done in this tab?")
                page.wait_for_url(base+"/done",timeout=6000)
                assert len(context.pages) == 1 and reply.kind == "action",reply.message
                result = {"native_same_tab_navigation":True,"tab_count":len(context.pages),
                          "reply":reply.message,"sections_rendered":8,"companion_survived_minimize":True,
                          "cloud_model_calls":0,"microphone_started":window.chat_page.voice_panel.controller.capture_active}
                assert not result["microphone_started"]
                (output/"Jarvis-interface-check.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
                print(json.dumps(result))
            finally:browser.close()
    finally:
        server.shutdown();server.server_close()
        window.close();qt.processEvents()


if __name__ == "__main__":main()
