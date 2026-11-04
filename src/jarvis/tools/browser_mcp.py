"""A narrow, permission-gated client for Microsoft's Playwright MCP server."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import ClassVar
from urllib.parse import urljoin

from mcp.client.stdio import StdioServerParameters

from jarvis.core.request_control import report_status
from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.mcp_client import StdioMCPClient, local_environment
from jarvis.tools.web_research import public_url

ALLOWED_TOOLS = {"browser_navigate", "browser_snapshot", "browser_tabs", "browser_navigate_back",
                 "browser_click","browser_type","browser_press_key"}


class BrowserActionUncertainError(ValueError):
    """An input was sent, but its result could not be observed. Never replay it."""


def load_snapshot(text):
    root = Path(__file__).resolve().parents[3]
    output = (root/".mcp/output").resolve()
    match = re.search(r"\[Snapshot\]\(([^)]+)\)", text)
    if match:
        path = (root/match[1]).resolve()
        if path.is_relative_to(output) and path.suffix in {".yml", ".yaml"} and path.is_file() and path.stat().st_size <= 200000:
            text += "\n" + path.read_text(encoding="utf-8")
    return text


def parse_snapshot(text):
    match = re.search(r"Page URL: (https?://[^\s]+)", text)
    url = match[1] if match else ""
    title = re.search(r"Page Title: ([^\n]+)", text)
    links = []
    label = ""
    for line in text.splitlines():
        if re.search(r"\blink ", line):
            label_match = re.search(r'link "([^"]*)"', line)
            label = label_match[1][:180] if label_match else "Link"
        target = re.search(r"/url: (.+)$", line)
        if target and label:
            address = urljoin(url, target[1].strip().strip('"'))
            if address.startswith("https://"):
                previous = next((l for l in links if l["url"] == address), None)
                if previous is None:
                    links.append({"label": label, "url": address})
                elif label not in previous["label"]:
                    previous["label"] = (previous["label"] + " / " + label)[:250]
            label = ""
    # Result cards expose a heading inside a link, or a link inside a heading.
    # Use accessibility structure, never provider/domain-specific CSS or a
    # guessed search URL. Navigation/footer links without headings stay separate.
    lines = text.splitlines()
    result_urls = set()
    headings = []
    for index, line in enumerate(lines):
        indent = len(line) - len(line.lstrip())
        while headings and headings[-1] >= indent:
            headings.pop()
        if re.search(r"\bheading .*\[level=[23]\]", line):
            headings.append(indent)
        if not re.search(r"\blink ", line):
            continue
        block = []
        for child in lines[index+1:]:
            if child.strip() and len(child)-len(child.lstrip()) <= indent:
                break
            block.append(child)
        if headings or any(re.search(r"\bheading .*\[level=[23]\]", child) for child in block):
            target = next((re.search(r"/url: (.+)$", child) for child in block if "/url:" in child), None)
            if target:
                result_urls.add(urljoin(url, target[1].strip().strip('"')))
    elements = {}
    for line in text.splitlines():
        ref = re.search(r"\[ref=(e\d+)\]",line)
        if ref:elements[ref[1]] = line.strip()[:500]
    return {"url": url, "title": title[1].strip()[:180] if title else "", "snapshot": text[:14000],"elements":elements,
            "links": links if len(links) <= 200 else links[:125] + links[-75:],
            "result_links":[link for link in links if link["url"] in result_urls][:100]}


class PlaywrightMCP(StdioMCPClient):
    def __init__(self, *, headless=False, mode="isolated", profile=""):
        self.headless,self.mode,self.profile = headless,mode,profile
        super().__init__("playwright",ALLOWED_TOOLS)

    def launch(self):
        root = self.root
        node = shutil.which("node") or str(Path.home()/"AppData/Local/hermes/node/node.exe")
        cli = root/".mcp/node_modules/@playwright/mcp/cli.js"
        if not cli.exists():raise ValueError("Playwright MCP is not installed. Open Settings → Integrations.")
        args = [str(cli),"--codegen","none","--timeout-navigation","15000","--timeout-action","10000",
                "--output-dir",str(root/".mcp/output")]
        if self.mode == "extension":
            args += ["--extension","--browser","chrome"]
            if self.profile:args += ["--profile-dir-name",self.profile]
        else:
            browsers = list((root/".browsers").glob("chromium-*/chrome-win64/chrome.exe"))
            if not browsers:raise ValueError("The Jarvis browser runtime is missing.")
            config = root/".mcp/browser-config.json"
            config.write_text(json.dumps({"browser":{"contextOptions":{"acceptDownloads":False}}}),encoding="utf-8")
            args += ["--config",str(config),"--isolated","--executable-path",str(browsers[-1]),"--block-service-workers"]
            if self.headless:args.append("--headless")
        return StdioServerParameters(command=node,args=args,env=local_environment(),cwd=str(root))

    def decode_result(self,value):
        return load_snapshot(super().decode_result(value)["text"])

    def configure(self,mode,profile=""):
        if mode not in {"isolated","extension"}:raise ValueError("Choose a supported browser connection.")
        if mode != self.mode or profile != self.profile:
            self.close()
            if self.thread is not None:raise ValueError("A browser operation is still stopping. Try changing the connection again shortly.")
            self.mode,self.profile = mode,profile


class BrowserMCPTool(Tool):
    name = "browser_mcp"
    description = "Navigate, observe and select tabs through Playwright MCP. Keep the current selected tab unless asked to change it."
    required_capability = Capability.USE_BROWSER
    parameters_schema: ClassVar[dict[str, object]] = {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["navigate", "snapshot", "follow_link", "tabs", "back","select_tab"]},
        "url": {"type": "string"}, "link_index": {"type": "integer"},
        "link_kind":{"type":"string","enum":["link","result"]},"tab_index":{"type":"integer","minimum":0}}, "required": ["action"], "additionalProperties": False}

    def __init__(self, client=None):
        self.client = client or PlaywrightMCP()
        self.last = {"url": "", "snapshot": "", "links": []}

    def execute(self, arguments):
        action = arguments.get("action")
        if action == "tabs":
            return {"ok": True, "tabs": self.client.call("browser_tabs", {"action": "list"})}
        if action == "select_tab":
            index = arguments.get("tab_index")
            if type(index) is not int or index<0:raise ValueError("Choose an observed zero-based browser tab index.")
            tabs = self.client.call("browser_tabs",{"action":"list"})
            if not re.search(rf"(?m)^-\s*{index}:\s",tabs):raise ValueError("That tab is not available in the connected browser.")
            self.client.call("browser_tabs",{"action":"select","index":index})
            text = self.client.call("browser_snapshot",{})
        elif action == "snapshot":
            text = self.client.call("browser_snapshot", {})
        elif action == "back":
            text = self.client.call("browser_navigate_back", {})
        elif action in {"navigate", "follow_link"}:
            url = arguments.get("url", "")
            if action == "follow_link":
                index = arguments.get("link_index")
                links = self.last.get("result_links", []) if arguments.get("link_kind") == "result" else self.last["links"]
                if type(index) is not int or not 1 <= index <= len(links):
                    raise ValueError("Choose an observed link number from the latest snapshot.")
                url = links[index - 1]["url"]
                fresh = parse_snapshot(self.client.call("browser_snapshot", {}))
                current = fresh.get("result_links", []) if arguments.get("link_kind") == "result" else fresh["links"]
                if fresh["url"] != self.last["url"] or index > len(current) or current[index-1]["url"] != url:
                    self.last = fresh
                    raise ValueError("The page changed. Use the new snapshot before following a link.")
            if not isinstance(url, str) or not public_url(url):
                raise ValueError("Navigation requires a public HTTPS URL without credentials.")
            report_status("Navigating browser through Playwright MCPâ€¦")
            text = self.client.call("browser_navigate", {"url": url})
        else:
            raise ValueError("Choose navigate, snapshot, follow_link, or tabs.")
        self.last = parse_snapshot(text)
        if action in {"navigate","follow_link","back","select_tab"} and not self.last["url"]:
            raise ValueError("The browser did not confirm a loaded page. I can't verify that navigation completed.")
        if self.last["url"] and not public_url(self.last["url"]):
            self.last = {"url": "", "snapshot": "", "links": []}
            raise ValueError("The browser redirected outside the public HTTPS navigation policy.")
        return {"ok": True, **self.last}

    def close(self):
        self.client.close()


class BrowserClickTool(Tool):
    name = "browser_click"
    internal_only = True
    description = "Click one exact element reference from the latest browser snapshot. Stay in the current tab."
    required_capability = Capability.CLICK_UI
    additional_capabilities = (Capability.USE_BROWSER,)
    parameters_schema: ClassVar[dict[str,object]] = {"type":"object","properties":{"target":{"type":"string"}},"required":["target"],"additionalProperties":False}

    def __init__(self,browser):self.browser = browser

    def execute(self,arguments):
        target = arguments.get("target")
        old = self.browser.last
        if not isinstance(target,str) or not re.fullmatch(r"e\d+",target) or target not in old.get("elements",{}):
            raise ValueError("Choose an exact element reference from the latest browser snapshot.")
        fresh = self.browser.execute({"action":"snapshot"})
        if fresh.get("url") != old.get("url") or fresh.get("elements",{}).get(target) != old["elements"][target]:
            raise ValueError("The browser page changed. Choose a target from the fresh snapshot.")
        try:
            self.browser.client.call(self.name,self._arguments(target,arguments))
            return self.browser.execute({"action":"snapshot"})
        except ValueError as error:
            raise BrowserActionUncertainError("I sent the browser input but couldn't verify its result. I stopped without repeating it.") from error

    def _arguments(self,target,arguments):return {"target":target}


class BrowserTypeTool(BrowserClickTool):
    name = "browser_type"
    description = "Fill an observed browser text field. Does not submit it or press Enter."
    required_capability = Capability.TYPE_TEXT
    parameters_schema: ClassVar[dict[str,object]] = {"type":"object","properties":{"target":{"type":"string"},"text":{"type":"string","maxLength":10000}},"required":["target","text"],"additionalProperties":False}

    def execute(self,arguments):
        text = arguments.get("text")
        if not isinstance(text,str) or len(text)>10000 or any(ord(c)<32 and c not in "\n\t" for c in text):
            raise ValueError("Browser input must be bounded literal text.")
        return super().execute(arguments)

    def _arguments(self,target,arguments):return {"target":target,"text":arguments["text"],"submit":False}


class BrowserKeyTool(Tool):
    name = "browser_key"
    internal_only = True
    description = "Press a navigation key in the observed browser. Enter can submit the focused field; use only when requested."
    required_capability = Capability.KEYBOARD_ACTION
    additional_capabilities = (Capability.USE_BROWSER,)
    KEYS = ("Enter","Escape","Tab","ArrowDown","ArrowUp","ArrowLeft","ArrowRight","PageDown","PageUp","Home","End","Space")
    parameters_schema: ClassVar[dict[str,object]] = {"type":"object","properties":{"key":{"type":"string","enum":list(KEYS)}},"required":["key"],"additionalProperties":False}

    def __init__(self,browser):self.browser = browser

    def execute(self,arguments):
        key = arguments.get("key")
        if key not in self.KEYS:raise ValueError("Choose an available browser navigation key.")
        old = self.browser.last
        if not old.get("url"):raise ValueError("Observe a browser page before sending a key.")
        fresh = self.browser.execute({"action":"snapshot"})
        if old.get("url") != fresh.get("url"):raise ValueError("The selected browser page changed. Observe before pressing a key.")
        try:
            self.browser.client.call("browser_press_key",{"key":key})
            return self.browser.execute({"action":"snapshot"})
        except ValueError as error:
            raise BrowserActionUncertainError("I sent the browser key but couldn't verify its result. I stopped without repeating it.") from error
