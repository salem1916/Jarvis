"""Grounded conversation state and separate spoken, visible, and detailed replies."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from jarvis.core.browser_commands import search_description
from jarvis.core.search_intent import SearchIntent, SearchMemory


@dataclass(frozen=True)
class Choice:
    label: str
    url: str


@dataclass(frozen=True)
class AssistantEvent:
    stage: str
    message: str
    tool: str = ""
    url: str = ""
    choices: tuple[Choice, ...] = ()
    target: str = ""
    operation: str = ""


@dataclass(frozen=True)
class AssistantReply:
    kind: str
    message: str
    spoken_text: str
    details: str
    events: tuple[AssistantEvent, ...] = ()
    choices: tuple[Choice, ...] = ()


@dataclass(frozen=True)
class PreparedTurn:
    prompt: str
    clarification: str = ""
    choices: tuple[Choice, ...] = ()
    resume_url: str = ""
    kind: str = "clarification"
    opening: str = ""
    reference: AssistantEvent | None = None
    agent_prefix: str = ""
    search: SearchIntent | None = None


def page_label(url: str) -> str:
    host = (urlsplit(url).hostname or "website").removeprefix("www.")
    return {"google.com": "Google", "youtube.com": "YouTube", "github.com": "GitHub"}.get(host, host)


def short_reply(text: str, limit: int = 360, *, sentence_limit: int = 2) -> str:
    text = re.split(r"\n\n(?:Pages observed|Sources read|Research notes):", text, maxsplit=1)[0]
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "the page", text)
    text = re.sub(r"[*#`]+", "", text)
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"(?m)^\s*[-+]\s+", "", text)
    text = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    summary = " ".join(sentences[:sentence_limit]) if sentence_limit else text
    if len(summary) > limit:
        summary = summary[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return summary


def action_event(tool: str, arguments, result=None) -> AssistantEvent:
    url = str(arguments.get("url", ""))
    target = str(arguments.get("application", arguments.get("path", "")))
    if tool == "open_url":
        if isinstance(result, dict):
            url = str(result.get("url", url))
            target = str(result.get("title", ""))[:180]
        search = search_description(url)
        if search:
            message = search if result is not None else search.replace("Opened", "Opening", 1) + "…"
        else:
            message = f"Opened {page_label(url)}." if result is not None else f"Opening {page_label(url)}…"
        if isinstance(result, dict) and result.get("current_tab"):
            message = (search.rstrip(".") if search else f"Opened {page_label(url)}") + " in your current Chrome tab."
    elif tool == "current_chrome_navigation":
        if arguments.get("action") == "list_tabs":
            if result is not None:
                return AssistantEvent("observed", "Read open regular Chrome tabs.", tool)
            return AssistantEvent("working", "Checking open Chrome tabs…", tool)
        url = str(result.get("url", "")) if isinstance(result, dict) else ""
        if url:
            verb = "Went back to" if arguments.get("action") == "back" else "Opened"
            target = "the requested video" if arguments.get("link_kind") == "video" else page_label(url)
            message = f"{verb} {target} in your current Chrome tab."
        else:
            message = "Using your current Chrome tab…"
    elif tool == "open_application":
        name = str(result.get("application", target)) if isinstance(result, dict) else target
        message = f"{name} is opening." if result is not None else f"Opening {name}…"
    elif tool in {"browser_mcp","browser_click","browser_type","browser_key"}:
        url = str(result.get("url", "")) if isinstance(result, dict) else ""
        target = str(result.get("title", ""))[:180] if isinstance(result, dict) else ""
        label = target or page_label(url)
        if isinstance(result, dict) and result.get("background"):
            message = f"Read {label} in the background." if url else "No public page was observed."
            return AssistantEvent("observed", message, tool, url, target=target, operation=arguments.get("action"))
        operation = arguments.get("action")
        if not url:
            message = "Checked the available browser tabs." if result is not None and operation == "tabs" else "Working in the browser…"
        elif tool == "browser_type":
            message = f"Entered text on {label}."
        elif tool == "browser_key":
            message = f"Used {arguments.get('key', 'the requested key')} on {label}."
        elif tool == "browser_click":
            message = f"Clicked the requested control on {label}."
        elif operation == "back":
            message = f"Went back to {label}."
        elif operation in {"navigate", "follow_link"}:
            message = f"Opened {label}."
        else:
            message = f"Read {label}."
    elif tool == "research_web":
        message = "Search results received." if result is not None else "Looking for relevant sources…"
    elif tool in {"read_file", "write_file"}:
        target = str(result.get("path", target)) if isinstance(result, dict) else target
        verb = "Read" if tool == "read_file" else "Saved"
        message = f"{verb} {Path(target).name}." if result is not None else f"Working on {Path(target).name}…"
    elif tool in {"observe_screen","windows_snapshot"}:
        message = "Observed the shared window." if result is not None else "Looking at the shared window…"
    elif tool in {"list_ui_elements", "list_open_windows"}:
        message = "Read the available app controls." if result is not None else "Checking available app controls…"
    elif tool in {"click_ui_element", "keyboard_action", "type_text", "control_window"}:
        target = str(arguments.get("window", ""))
        operation = str(arguments.get("element", arguments.get("action", "text input")))
        message = f"Used {operation} in {target}." if result is not None else f"Working in {target}…"
    else:
        message = "Action completed." if result is not None else "Working on your request…"
    return AssistantEvent("action_done" if result is not None else "working", message, tool, url,
                          target=(str(result.get("application", target)) if isinstance(result, dict) else target) if result is not None else "",
                          operation=str(arguments.get("action", tool)))


def build_reply(text: str, events, *, error: Exception | None = None) -> AssistantReply:
    recorded = tuple(events)
    completed = [event for event in recorded if event.stage == "action_done"]
    choices = next((event.choices for event in reversed(recorded) if event.stage == "clarification"), ())
    if error is not None:
        from jarvis.core.action_confirmation import ActionDeclinedError
        from jarvis.core.request_control import RequestCancelledError
        from jarvis.models.connection_errors import (
            ProviderConnectionError,
            rate_limit_message,
        )
        if isinstance(error, RequestCancelledError):
            message, kind = "Stopped.", "cancelled"
        elif isinstance(error, ActionDeclinedError):
            message, kind = "Okay. I didn't perform that action.", "cancelled"
        else:
            message, kind = "I couldn't finish that request.", "partial" if completed else "failed"
            if isinstance(error, ProviderConnectionError):
                message = short_reply(str(error), 340)
            elif isinstance(error, PermissionError):
                message = "That action isn't allowed by the current permissions."
                from jarvis.security.capabilities import Capability
                capability = next((cap.value for cap in Capability if cap.value in str(error)), "")
                message += f" Enable {capability.replace('_', ' ').title()} in Permissions." if capability else " " + str(error)[:180]
            elif isinstance(error, (ValueError, KeyError)) and str(error):
                message = short_reply(str(error), 340)
        actions = [event for event in completed if event.tool not in {"observe_screen","windows_snapshot","list_ui_elements","list_open_windows"}]
        receipts = " ".join(dict.fromkeys(event.message for event in actions))
        if isinstance(error, ProviderConnectionError) and error.status_code == 429:
            message = ((receipts + " ") if receipts else "") + rate_limit_message(error)
            recorded += (AssistantEvent("blocked", message, operation="provider_limit"),)
        elif receipts:
            message += " " + receipts
        return AssistantReply(kind, message, message, text, recorded)
    if any(event.stage == "clarification" for event in recorded):
        return AssistantReply("clarification", text, short_reply(text), text, recorded, choices)
    if text.startswith(("Task partly completed", "Task not completed", "The browser reached")):
        message = next((event.message for event in reversed(recorded) if event.stage == "blocked"), "") or short_reply(text, sentence_limit=0)
        return AssistantReply("partial", message, message, text, recorded)
    if completed:
        spoken = next((event.message for event in reversed(recorded) if event.stage == "summary"), "")
        if text.startswith("Opened ") and len(completed) == 1 and completed[0].tool in {"open_url", "open_application"}:
            message = completed[0].message
        else:
            message = short_reply(spoken or text, sentence_limit=0 if spoken else 2) or completed[-1].message
        return AssistantReply("action", message, message, text, recorded)
    summary = next((event.message for event in reversed(recorded) if event.stage == "summary"), "")
    return AssistantReply("answer", summary or text, short_reply(summary or text, sentence_limit=0 if summary else 2), text, recorded)


@dataclass
class InteractionSession:
    focus_url: str = ""
    focus_application: str = ""
    focus_file: str = ""
    choices: tuple[Choice, ...] = ()
    selected_url: str = ""
    pending_open: bool = False
    selecting: bool = False
    last_kind: str = ""
    completed: list[AssistantEvent] = field(default_factory=list)
    retry_turn: PreparedTurn | None = None
    search_memory: SearchMemory = field(default_factory=SearchMemory)

    def record(self, reply: AssistantReply) -> None:
        self.last_kind = "reference" if any(e.stage == "reference" for e in reply.events) else reply.kind
        for event in reply.events:
            if event.stage == "reference":
                self.focus_url = event.url
                self.focus_application = event.target if event.tool == "open_application" else ""
            if event.stage == "action_done":
                self.completed.append(event)
                if event.url:
                    self.focus_url = event.url
                    self.focus_application = ""
                    self.focus_file = ""
                    self.selected_url = event.url
                    if self.choices and event.url not in {choice.url for choice in self.choices}:
                        self.choices = ()
                elif event.tool == "open_application":
                    self.focus_application = event.target
                    self.focus_url = ""
                    self.choices = ()
                    self.focus_file = ""
                elif event.tool in {"read_file", "write_file"}:
                    self.focus_file = event.target
                    self.focus_url = self.focus_application = ""
                    self.choices = ()
                elif event.tool in {"close_window", "trash_file"}:
                    self.focus_url = self.focus_application = self.focus_file = ""
                    self.choices = ()
            if event.stage == "sources":
                self.choices = event.choices
                self.selected_url = ""
            if event.stage == "clarification" and event.choices:
                self.choices = event.choices
                self.selecting = True
        self.completed = self.completed[-20:]

    def _choose(self) -> PreparedTurn:
        self.selecting = True
        question = "Which page do you mean?" if self.choices else "Which page, app, or file do you mean?"
        return PreparedTurn("", question, self.choices[:5])

    def prepare(self, prompt: str, router, browser_url: str = "", *, current_chrome: bool = False) -> PreparedTurn:
        text = re.sub(r"^(?:[0-9]+[.)]|[-*+])\s+", "", prompt.strip())
        from jarvis.core.navigation_reference import navigation_reference
        if navigation_reference(text) and browser_url and browser_url == self.focus_url:
            return PreparedTurn("browser: " + text, resume_url=browser_url, kind="navigation")
        text = re.sub(r"^(?:actually[, ]+|instead[, ]+|stop[.!;,]\s*)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:can|could|would) you (?:please )?not (?=(?:open|launch|visit|click|type|close|delete)\b)", "do not ", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:can|could|would) you (?:please )?(?=(?:open|read|summari[sz]e|check|find|look|visit|try|retry|continue)\b)", "", text, flags=re.IGNORECASE)
        if re.match(r"(?:open|launch|visit|read|summarize)\b", text, re.IGNORECASE):
            text = re.sub(r"\s+instead[.!]?$", "", text, flags=re.IGNORECASE)
        normalized = text.casefold().strip(" .!?")
        if re.fullmatch(r"(?:please )?(?:try again|retry|continue|carry on)", normalized):
            previous = self.retry_turn
            if previous is None:
                return PreparedTurn("", "Which task would you like me to continue?")
            if previous.search is not None:
                return previous
            if previous.prompt.startswith("browser:"):
                return PreparedTurn(previous.prompt, resume_url=browser_url if browser_url == self.focus_url else "", agent_prefix=previous.agent_prefix)
            if previous.prompt.startswith("research "):
                return previous
            return PreparedTurn("", "Which part would you like me to retry? I won't repeat completed actions automatically.")
        if normalized in {"what did you just read", "what did you read", "what page did you read", "which page did you read"}:
            read = next((event for event in reversed(self.completed) if event.tool == "browser_mcp" and event.url), None)
            message = f"I just read {read.target or page_label(read.url)}." if read else "I haven't read a page in this conversation yet."
            return PreparedTurn("", message, kind="answer", reference=AssistantEvent("reference", message, "browser_mcp", read.url) if read else None)
        if normalized in {"what did you just open", "what did you open", "what have you opened"}:
            opened = next((event for event in reversed(self.completed) if event.tool in {"open_url", "open_application", "browser_click", "current_chrome_navigation"}
                           or (event.tool == "browser_mcp" and event.operation in {"navigate", "follow_link", "back"})), None)
            return PreparedTurn("", opened.message if opened else "I haven't opened anything in this conversation yet.", kind="answer",
                                reference=AssistantEvent("reference", opened.message, opened.tool, opened.url, target=opened.target) if opened else None)
        if re.match(r"^(?:please )?(?:don't|do not|never) (?:open|launch|visit|click|type|close|delete)\b", normalized) and not re.search(r"\b(and|then|instead)\b", normalized):
            self.pending_open = self.selecting = False
            return PreparedTurn("", "Okay. No action taken.", kind="answer")
        if normalized in {"stop", "cancel", "stop please"} and not self.pending_open and not self.selecting:
            return PreparedTurn("", "No task is running.", kind="answer")
        if normalized in {"cancel", "never mind", "nevermind", "no"} and (self.pending_open or self.selecting):
            self.pending_open = self.selecting = False
            return PreparedTurn("", "Okay. No action taken.", kind="answer")
        if self.pending_open:
            if normalized in {"yes", "sure", "okay", "ok"}:
                return PreparedTurn("", "Which application or website should I open?")
            self.pending_open = False
            informational = re.match(r"(?:what|why|how|who|where|when|explain|tell|can|could|would|do|does|is|are|remember|forget|research|search|don't|do not)\b", text, re.IGNORECASE)
            if not informational and not text.endswith("?") and len(text.split()) <= 5 and router.route("open " + text) is not None and not re.match(r"(?:open|launch|visit)\b", text, re.IGNORECASE):
                return PreparedTurn("open " + text)
        if normalized in {"open", "open something", "launch", "open it", "open that", "open this"}:
            if (normalized in {"open it", "open that", "open this"} and self.last_kind in {"action", "reference"}
                    and (self.focus_url or self.focus_application)):
                return PreparedTurn("open " + (self.focus_url or self.focus_application))
            self.pending_open = True
            return PreparedTurn("", "What would you like me to open?")
        match = re.fullmatch(r"(?:(open|read|summari[sz]e) )?(?:the )?(first|second|third|fourth|fifth|other|[1-5])(?: (?:one|page|result|link|item|thing))?", normalized)
        if self.selecting and normalized in {"yes", "sure", "okay", "ok"}:
            return self._choose()
        if match and (match[1] or self.selecting):
            index = {"first":0, "second":1, "third":2, "fourth":3, "fifth":4}.get(match[2])
            if match[2].isdigit():
                index = int(match[2]) - 1
            if match[2] == "other" and len(self.choices) == 2 and self.selected_url in {c.url for c in self.choices}:
                index = next(i for i, c in enumerate(self.choices) if c.url != self.selected_url)
            if not self.choices and self.focus_url and search_description(self.focus_url):
                return PreparedTurn(f"browser: Open {self.focus_url} and {text}")
            if index is None or index >= len(self.choices):
                return self._choose()
            self.selecting = False
            chosen = self.choices[index]
            verb = match[1] or "open"
            return PreparedTurn("open " + chosen.url if verb == "open" else f"browser: Open {chosen.url} and {verb} the page")
        reference = bool(re.search(r"\b(?:this|that|the|current|same) (?:page|website|site)\b", normalized)
                         or re.match(r"(?:please )?(?:read|summari[sz]e|check) (?:it|that)(?:$|[ .!?])", normalized)
                         or re.match(r"(?:please )?(?:find|look for|check) (?:its|their)\b", normalized))
        reading = bool(re.match(r"(?:please )?(?:read|summari[sz]e|check|find|look at|look for|tell me about)\b", normalized))
        if reading and reference and "https://" not in normalized:
            explicit_page = re.search(r"\b(?:page|website|site)\b", normalized)
            if self.focus_file and not explicit_page:
                return PreparedTurn(text + ". Use the file at " + json.dumps(self.focus_file) + ".")
            if current_chrome:
                return PreparedTurn("browser: " + text)
            if not self.focus_url:
                return self._choose()
            self.selecting = False
            if browser_url == self.focus_url:
                return PreparedTurn("browser: " + text, resume_url=self.focus_url)
            return PreparedTurn(f"browser: Open {self.focus_url} and {text}")
        # A natural two-part website instruction uses the same browser workflow.
        compound = re.match(r"^(.+?)\s+(?:and then|and|then)\s+(.+)$", text, re.IGNORECASE)
        if compound:
            opening = router.route(compound[1])
            if opening is not None and opening.tool_name == "open_url" and re.match(r"(?:read|find|summari[sz]e|look for|look at|check|inspect|see|show|search|compare|extract)\b", compound[2], re.IGNORECASE):
                url = str(opening.arguments["url"])
                return PreparedTurn(f"browser: Open {url} and {compound[2]}")
        if self.focus_url and re.match(r"(?:you (?:have|need) to|please) search(?:[.!?]|$)", normalized):
            return PreparedTurn(f"browser: Open {self.focus_url} and complete the search from my latest request. {text}")
        self.selecting = False
        return PreparedTurn(text)
