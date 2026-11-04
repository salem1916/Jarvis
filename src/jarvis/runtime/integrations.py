"""User-selected local integrations. Connections start only on explicit use."""
import os
import re
from importlib.util import find_spec

from jarvis.tools.browser_mcp import BrowserMCPTool
from jarvis.tools.windows_mcp import WindowsSnapshotTool


class Integrations:
    def __init__(self,app):
        self.app = app
        self.grounded_planner_available = find_spec("pydantic_ai") is not None and find_spec("groq") is not None
        self.grounded_planner = self.grounded_planner_available and os.getenv("JARVIS_BROWSER_PLANNER") == "grounded"
        browser = app.tool_service.registry.get("browser_mcp")
        snapshot = app.tool_service.registry.get("windows_snapshot")
        if not isinstance(browser,BrowserMCPTool) or not isinstance(snapshot,WindowsSnapshotTool):
            raise TypeError("The local integration adapters are unavailable.")
        self.browser = browser
        self.windows = snapshot.backend
        records = app.personal_memory.records("integrations")
        prefs = records[0] if records else {}
        mode = os.getenv("JARVIS_BROWSER_MODE") or prefs.get("browser_mode", "isolated")
        self.apply(mode,prefs.get("profile",""),prefs.get("windows_enabled",False),save=False)

    def apply(self,mode,profile,windows_enabled,*,save=True):
        if mode not in {"system","isolated","extension"}:raise ValueError("Choose a browser connection in Settings.")
        if not isinstance(profile,str) or not re.fullmatch(r"[\w .-]{0,80}",profile):raise ValueError("Use a Chrome profile directory name, such as Default or Profile 1.")
        if (mode, profile.strip()) != (self.browser.client.mode, self.browser.client.profile):
            self.browser.client.configure(mode,profile.strip())
            self.browser.last = {"url": "", "snapshot": "", "links": []}
        if not windows_enabled:self.windows.close()
        self.windows.enabled = bool(windows_enabled)
        if save:
            self.app.personal_memory.save_record("integrations","main",{
                "browser_mode":mode,"profile":profile.strip(),"windows_enabled":bool(windows_enabled)})

    def status(self):
        return {"browser_mode":self.browser.client.mode,"profile":self.browser.client.profile,
                "windows_enabled":self.windows.enabled,"windows_installed":bool(self.windows.client.command)}
