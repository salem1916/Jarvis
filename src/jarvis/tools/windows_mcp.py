"""Optional Windows-MCP adapters behind Jarvis capture and capability gates."""
import re
import time
from typing import ClassVar

import win32gui

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.mcp_client import StdioMCPClient
from jarvis.tools.screen_observation import _capture_owner


class WindowsMCP:
    def __init__(self,screen,client=None):
        self.screen = screen
        self.enabled = False
        self.last = None
        if client is None:
            from pathlib import Path
            root = Path(__file__).resolve().parents[3]
            python = root/".windows-venv/Scripts/python.exe"
            client = StdioMCPClient("windows",{"Snapshot","Click","Type","Scroll"},
                command=str(python) if python.exists() else "",
                args=["-m","windows_mcp","serve","--transport","stdio","--tools","Snapshot,Click,Type,Scroll"],
                env={"ANONYMIZED_TELEMETRY":"false","POSTHOG_API_KEY":"","PYTHONIOENCODING":"utf-8"},timeout=35)
        self.client = client

    def _check(self):
        if not self.enabled:raise ValueError("Windows-MCP is off. Enable it in Settings → Integrations.")
        if not self.screen.enabled:raise PermissionError("Screen access is off. Enable it before desktop control.")

    def snapshot(self,*,vision=False,scope="active_app"):
        self._check()
        handle = self.screen.resolve_window()
        if scope != "desktop" and (not handle or not win32gui.IsWindow(handle)):
            raise ValueError("Bring the app you want to use forward first.")
        region = list(win32gui.GetWindowRect(handle)) if scope != "desktop" else None
        if scope != "desktop" and win32gui.GetForegroundWindow() != handle:
            # Windows-MCP inspects the foreground app. Focusing the trusted,
            # remembered app prevents capturing Jarvis laid over its region.
            win32gui.SetForegroundWindow(handle)
            if win32gui.GetForegroundWindow() != handle:raise ValueError("The shared app could not be brought forward.")
        args: dict[str,object] = {"use_vision":vision,"use_annotation":False,"use_ui_tree":True,"use_dom":False}
        if region:args["region"] = region
        result = self.client.call("Snapshot",args)
        self._check()
        text = result["text"]
        tree = text.split("UI Tree:",1)[-1]
        # Do not forward unrelated open-window titles from the server metadata.
        title = win32gui.GetWindowText(handle) if scope != "desktop" else "Current display"
        self.last = {"handle":handle,"title":title,"region":region,"tree":tree,"at":time.monotonic(),"scope":scope}
        page = {"ok":True,"window":title,"controls":tree[:14000],"backend":"Windows-MCP"}
        if vision:
            if not result["images"]:raise ValueError("Windows-MCP did not return the requested image.")
            page["image"] = result["images"][0]
        return page

    def act(self,name,arguments):
        self._check()
        old = self.last
        if not old or time.monotonic()-old["at"]>30:raise ValueError("Observe the app again before acting.")
        x,y = arguments.get("x"),arguments.get("y")
        if type(x) is not int or type(y) is not int:raise ValueError("Use integer coordinates from the current observed app.")
        if old["scope"] == "desktop":raise ValueError("Observe the intended active app before controlling it.")
        handle = self.screen.resolve_window()
        if handle != old["handle"] or not win32gui.IsWindow(handle):raise ValueError("The active app changed. Observe before acting.")
        rect = list(win32gui.GetWindowRect(handle))
        if rect != old["region"] or not rect[0]<=x<rect[2] or not rect[1]<=y<rect[3]:
            raise ValueError("The app moved or the target is outside the observed app.")
        self.snapshot(scope=old["scope"])
        fresh = self.last
        if fresh is None or fresh["tree"] != old["tree"]:raise ValueError("The app controls changed. Use the fresh observation before acting.")
        values: dict[str,object] = {"loc":[x,y]}
        if name == "Click":values.update({"button":"left","clicks":1})
        elif name == "Type":
            text = arguments.get("text")
            if not isinstance(text,str) or len(text)>10000 or re.search(r"[\x00-\x08\x0b-\x1f]",text):raise ValueError("Use bounded literal text.")
            values.update({"text":text,"clear":False,"press_enter":False})
        elif name == "Scroll":
            direction = arguments.get("direction")
            if direction not in {"up","down"}:raise ValueError("Choose up or down.")
            values.update({"direction":direction,"type":"vertical","wheel_times":2})
        else:raise ValueError("This Windows operation is not exposed.")
        result = self.client.call(name,values)
        self.last = None
        return {"ok":True,"operation":name,"window":old["title"],"result":result["text"][:1500]}

    def close(self):self.last = None;self.client.close()


class WindowsSnapshotTool(Tool):
    name = "windows_snapshot"
    internal_only = True
    description = "Inspect the shared active app with Windows-MCP. Returns real controls and screen coordinates."
    required_capability = Capability.INSPECT_UI
    additional_capabilities = (Capability.CONTROL_APPLICATION,)
    parameters_schema: ClassVar[dict[str,object]] = {"type":"object","properties":{"scope":{"type":"string","enum":["active_app","desktop"]},"vision":{"type":"boolean"}},"additionalProperties":False}

    def __init__(self,backend):self.backend = backend

    def execute(self,arguments):
        if _capture_owner.get() is not self.backend.screen:raise PermissionError("Desktop observations require the trusted screen workflow.")
        return self.backend.snapshot(vision=arguments.get("vision") is True,scope=arguments.get("scope","active_app"))

    def close(self):self.backend.close()


class WindowsClickTool(Tool):
    name = "windows_click"
    internal_only = True
    operation = "Click"
    description = "Click once at exact screen coordinates from the current Windows-MCP observation, inside the shared active app."
    required_capability = Capability.CLICK_UI
    additional_capabilities = (Capability.INSPECT_UI,Capability.CONTROL_APPLICATION)
    parameters_schema: ClassVar[dict[str,object]] = {"type":"object","properties":{"x":{"type":"integer"},"y":{"type":"integer"}},"required":["x","y"],"additionalProperties":False}

    def __init__(self,backend):self.backend = backend
    def execute(self,arguments):return self.backend.act(self.operation,arguments)


class WindowsTypeTool(WindowsClickTool):
    name = "windows_type"
    operation = "Type"
    description = "Type bounded literal text into the observed app field at x,y. Does not submit or press Enter."
    required_capability = Capability.TYPE_TEXT
    parameters_schema: ClassVar[dict[str,object]] = {"type":"object","properties":{"x":{"type":"integer"},"y":{"type":"integer"},"text":{"type":"string","maxLength":10000}},"required":["x","y","text"],"additionalProperties":False}


class WindowsScrollTool(WindowsClickTool):
    name = "windows_scroll"
    operation = "Scroll"
    description = "Scroll up or down inside the currently observed active app region at x,y."
    required_capability = Capability.KEYBOARD_ACTION
    parameters_schema: ClassVar[dict[str,object]] = {"type":"object","properties":{"x":{"type":"integer"},"y":{"type":"integer"},"direction":{"type":"string","enum":["up","down"]}},"required":["x","y","direction"],"additionalProperties":False}
