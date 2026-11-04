"""Compare the current Jarvis entry point with the experimental planner."""

import argparse
import asyncio
import json
import os
import site
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

JARVIS = Path(__file__).resolve().parents[2]
sys.path.append(str(JARVIS / "src"))
base_venv = Path(os.environ.get("JARVIS_BASE_VENV", str(JARVIS / ".venv")))
site.addsitedir(str(base_venv / "Lib/site-packages"))

import httpx
from groq import AsyncGroq
from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings, load_settings
from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_control import RequestControl, RetryBudget
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.runtime.intelligence import IntelligenceHub
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from planner import Prototype
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

HOME_PAGE = "https://fixture.example/start"
GUIDE = "https://fixture.example/returns"
QUESTION = "browser: Show me the returns guide and tell me the deadline."


class BrowserFixture:
    def __init__(self):
        self.url = ""
        self.history = []
        self.actions = []

    def call(self, name, args):
        if name == "browser_navigate":
            self.history.append(self.url)
            self.url = args["url"]
            self.actions.append(self.url)
        elif name == "browser_navigate_back":
            self.url = self.history.pop()
            self.actions.append(self.url)
        elif name != "browser_snapshot":
            raise ValueError("The fixture supports navigation and snapshots.")
        if self.url == HOME_PAGE:
            return (
                f"Page URL: {self.url}\nPage Title: Store help\n"
                '- link "Shipping guide" [ref=e1]:\n  - /url: /shipping\n'
                '  - heading "Shipping guide" [level=3]\n'
                '- link "Returns guide" [ref=e2]:\n  - /url: /returns\n'
                '  - heading "Returns guide" [level=3]\n'
            )
        if self.url == GUIDE:
            return (
                f"Page URL: {self.url}\nPage Title: Returns guide\n"
                "- paragraph: Returns must arrive within 37 days.\n"
                "- paragraph: Keep the receipt.\n"
                "- paragraph: Use the original box.\n"
                "- paragraph: Include the order number.\n"
                "- paragraph: Ask for a return label."
            )
        return f"Page URL: {self.url}\nPage Title: Shipping guide\n- paragraph: Orders ship in 4 days."

    def close(self):
        pass


class WireLog:
    def __init__(self, limit):
        self.limit = limit
        self.calls = 0
        self.tokens = 0
        self.statuses = []
        self.mode = "normal"
        self.control = None

    def count(self, request):
        if self.calls >= self.limit:
            raise RuntimeError("Comparison request budget reached.")
        self.calls += 1

    def fake(self, request):
        payload = json.loads(request.content)
        messages = payload["messages"]
        last = next(
            message["content"]
            for message in reversed(messages)
            if message["role"] == "user"
        )
        try:
            data = json.loads(last)
        except ValueError:
            data = {"request": last}
        page = data.get("page", {})
        on_guide = page.get("url") == GUIDE
        if self.mode == "outage" and on_guide:
            return httpx.Response(429, json={"error": {"message": "fixture quota"}})
        if self.mode == "interrupt":
            assert self.control is not None
            self.control.cancelled.set()
        if data.get("request") == "What is SQL?":
            answer = "SQL is a language for querying databases."
            decision = {"kind": "reply", "index": 0, "text": answer}
        elif on_guide:
            answer = "Returns must arrive within 37 days."
            if self.mode == "five_sources":
                answer = (
                    "1. Returns must arrive within 37 days.\n2. Keep the receipt.\n"
                    "3. Use the original box.\n4. Include the order number.\n5. Ask for a return label."
                )
            decision = {"kind": "reply", "index": 0, "text": answer}
        else:
            answer = ""
            decision = {
                "kind": "open_link",
                "index": 99 if self.mode == "bad_index" else 2,
                "text": "",
            }
        schema = payload.get("response_format", {}).get("json_schema", {}).get("name")
        if schema == "jarvis_controller_result":
            inner = (
                {"action": "finish", "answer": answer}
                if answer
                else {"action": "follow_link", "link_index": 2}
            )
            content = json.dumps({"result_json": json.dumps(inner)})
        elif schema:
            decision["evidence"] = [1] if on_guide and answer else []
            if on_guide and self.mode == "bad_evidence":
                decision["evidence"] = [999]
            if on_guide and self.mode == "five_sources":
                decision["evidence"] = [1, 2, 3, 4, 5]
            content = json.dumps(decision)
        else:
            content = answer
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "model": payload["model"],
                "created": 0,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    def usage(self, response):
        response.read()
        self.tokens += (
            response.json().get("usage", {}).get("total_tokens", 0)
            if response.is_success
            else 0
        )

    async def async_usage(self, response):
        await response.aread()
        self.usage(response)

    async def async_count(self, request):
        self.count(request)

    def status(self, response):
        self.statuses.append(response.status_code)

    async def async_status(self, response):
        self.status(response)


@contextmanager
def existing_groq():
    settings = load_settings()
    memory = PersonalMemory(settings.state_dir / "personal_memory.sqlite3")
    try:
        hub = IntelligenceHub(settings, memory)
        if hub.steward.policy()["enabled"]:
            raise RuntimeError(
                "Live comparison needs an adapter for the enabled API assistant policy."
            )
        key = hub.api_key("groq")
        if not key:
            raise RuntimeError("The saved Groq key is unavailable.")
        yield key, hub.model_for("groq"), hub.usage
    finally:
        memory.close()


def compare(lane, live, key, model_name, usage=None, limit=4):
    rows = []
    wire = WireLog(limit)
    sdk = None
    with tempfile.TemporaryDirectory(prefix="jarvis-planner-") as directory:
        root = Path(directory)
        app = build_application(
            JarvisSettings(workspace_dir=root, state_dir=root / "state")
        )
        browser = BrowserFixture()
        app.tool_service.registry.get("browser_mcp").client = browser
        for capability in (Capability.USE_BROWSER, Capability.OPEN_APPLICATION):
            app.tool_service.executor.policy.set_decision(
                capability, PermissionDecision.ALLOW
            )

        def record_usage(data, headers):
            wire.tokens += data.get("total_tokens", 0)
            if usage is not None:
                usage.record("groq", key, data, headers)

        # The baseline uses sync HTTP for test transports and async HTTP live.
        from jarvis.models.cancellable_http import provider_client

        @contextmanager
        def baseline_http(**kwargs):
            kwargs["event_hooks"] = {
                "request": [wire.async_count if live else wire.count],
                "response": [wire.async_status if live else wire.status],
            }
            if not live:
                kwargs["transport"] = httpx.MockTransport(wire.fake)
            with provider_client(**kwargs) as client:
                yield client

        try:
            baseline = OpenAICompatibleProvider(
                provider_name="groq",
                model=model_name,
                api_key=key,
                base_url="https://api.groq.com/openai/v1",
                timeout=15,
            )
            baseline.usage_callback = record_usage
            app.cloud_provider = app.local_worker_provider = baseline
            if lane == "prototype":

                async def account_usage(response):
                    wire.status(response)
                    await wire.async_usage(response)
                    if usage is not None and response.is_success:
                        usage.record(
                            "groq",
                            key,
                            response.json().get("usage", {}),
                            dict(response.headers),
                        )

                http = httpx.AsyncClient(
                    transport=None if live else httpx.MockTransport(wire.fake),
                    event_hooks={
                        "request": [wire.async_count],
                        "response": [account_usage],
                    },
                    limits=httpx.Limits(max_keepalive_connections=0),
                )
                sdk = AsyncGroq(
                    api_key=key, http_client=http, max_retries=0, timeout=15
                )
                model = GroqModel(model_name, provider=GroqProvider(groq_client=sdk))
                interact = Prototype(app, model).interact
            else:
                interact = lambda prompt, control: app.interact(
                    prompt, request_control=control
                )

            def turn(label, prompt, expected, *, mode="normal"):
                wire.mode = mode
                started = time.perf_counter()
                visible = []
                control = RequestControl(
                    input_source="voice" if label == "correction" else "text",
                    retry_budget=RetryBudget(limit=0),
                    on_event=lambda event: visible.append(time.perf_counter()),
                )
                wire.control = control
                before = (
                    wire.calls,
                    wire.tokens,
                    len(browser.actions),
                    len(wire.statuses),
                )
                result = interact(prompt, control)
                elapsed = time.perf_counter() - started
                rows.append(
                    {
                        "case": label,
                        "pass": bool(expected(result, browser.actions[before[2] :])),
                        "kind": result.kind,
                        "reply": result.message,
                        "requests": wire.calls - before[0],
                        "tokens": wire.tokens - before[1] if live else None,
                        "http_statuses": wire.statuses[before[3] :],
                        "actions": browser.actions[before[2] :],
                        "seconds": round(elapsed, 3),
                        "first_event_seconds": round(visible[0] - started, 3)
                        if visible
                        else None,
                    }
                )

            with (
                patch("jarvis.models.openai_compatible.provider_client", baseline_http),
                patch(
                    "jarvis.tools.browser_mcp.public_url",
                    lambda url: url.startswith("https://fixture.example/"),
                ),
                patch.object(
                    app.tool_service.registry.get("open_application"),
                    "execute",
                    lambda _: {"ok": True, "application": "Calculator"},
                ),
            ):
                turn(
                    "open_app",
                    "Open Calculator",
                    lambda r, _: r.kind == "action" and "Calculator" in r.message,
                )
                turn(
                    "question",
                    "What is SQL?",
                    lambda r, a: "database" in r.message.lower() and not a,
                )
                turn(
                    "open_page",
                    "Open " + HOME_PAGE,
                    lambda r, a: r.kind == "action" and a == [HOME_PAGE],
                )
                turn(
                    "show_and_answer",
                    QUESTION,
                    lambda r, a: "37 days" in r.message and a == [GUIDE],
                )
                if browser.url == GUIDE:
                    turn(
                        "correction",
                        "No, wait, go back",
                        lambda r, a: r.kind == "action" and a == [HOME_PAGE],
                    )
                else:
                    rows.append(
                        {
                            "case": "correction",
                            "pass": False,
                            "kind": "skipped",
                            "requests": 0,
                            "reason": "The preceding turn did not open the expected guide.",
                        }
                    )
                turn(
                    "ordinal",
                    "Open the second result",
                    lambda r, a: r.kind == "action" and a == [GUIDE],
                )
                if not live:
                    wire.calls = wire.tokens = 0
                    turn(
                        "reset",
                        "Open " + HOME_PAGE,
                        lambda r, a: r.kind == "action" and a == [HOME_PAGE],
                    )
                    turn(
                        "quota_after_action",
                        QUESTION,
                        lambda r, a: (
                            r.kind == "partial"
                            and a == [GUIDE]
                            and "limit" in r.message.lower()
                        ),
                        mode="outage",
                    )
                    turn(
                        "reset",
                        "Open " + HOME_PAGE,
                        lambda r, a: r.kind == "action" and a == [HOME_PAGE],
                    )
                    turn(
                        "cancel_late_decision",
                        QUESTION,
                        lambda r, a: r.kind == "cancelled" and not a,
                        mode="interrupt",
                    )
                    if lane == "prototype":
                        turn(
                            "reject_unobserved_link",
                            QUESTION,
                            lambda r, a: r.kind == "failed" and not a,
                            mode="bad_index",
                        )
                        wire.calls = wire.tokens = 0
                        turn(
                            "reject_unobserved_evidence",
                            QUESTION,
                            lambda r, a: (
                                r.kind == "partial"
                                and a == [GUIDE]
                                and "verify" in r.message
                            ),
                            mode="bad_evidence",
                        )
                        turn(
                            "retain_five_observed_sources",
                            QUESTION,
                            lambda r, a: (
                                r.kind == "answer"
                                and not a
                                and "Ask for a return label." in r.details
                            ),
                            mode="five_sources",
                        )
                        turn(
                            "reset",
                            "Open " + HOME_PAGE,
                            lambda r, a: r.kind == "action" and a == [HOME_PAGE],
                        )
                        wire.calls = wire.tokens = 0
                        turn(
                            "retain_numbered_browser_answer",
                            QUESTION,
                            lambda r, a: (
                                r.kind == "action"
                                and a == [GUIDE]
                                and "5. Ask for a return label." in r.message
                                and "5. Ask for a return label." in r.spoken_text
                            ),
                            mode="five_sources",
                        )
        finally:
            if sdk is not None:
                asyncio.run(sdk.close())
            app.shutdown()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the saved Groq connection, at most eight requests total.",
    )
    parser.add_argument(
        "--lane", choices=("both", "baseline", "prototype"), default="both"
    )
    parser.add_argument(
        "--request-limit",
        type=int,
        choices=(3, 4),
        default=4,
        help="Maximum live requests per lane.",
    )
    args = parser.parse_args()
    lanes = ("baseline", "prototype") if args.lane == "both" else (args.lane,)
    if args.live:
        with existing_groq() as (key, model, usage):
            results = {
                lane: compare(lane, True, key, model, usage, args.request_limit)
                for lane in lanes
            }
    else:
        model = "openai/gpt-oss-20b"
        results = {lane: compare(lane, False, "fixture-key", model) for lane in lanes}
    print(json.dumps({"live": args.live, "model": model, **results}, indent=2))
    if not args.live:
        local = {"open_app", "open_page", "correction", "ordinal", "reset"}
        for rows in results.values():
            assert all(row["pass"] for row in rows), "A controlled case failed."
            assert all(row["requests"] == 0 for row in rows if row["case"] in local)


if __name__ == "__main__":
    main()
