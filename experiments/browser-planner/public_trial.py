"""Exercise the experimental planner with real Playwright pages and bounded Groq usage."""

import argparse
import asyncio
import json
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from compare import WireLog, existing_groq
from groq import AsyncGroq
from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.request_control import RequestControl, RetryBudget
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.tools.browser_mcp import PlaywrightMCP
from planner import Prototype, page_context
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider


@dataclass(frozen=True)
class Site:
    name: str
    start: str
    goal: str
    destination: str
    answer_terms: tuple[str, ...]


SITES = (
    Site(
        "Python",
        "https://docs.python.org/3.14/",
        "Open the Python tutorial and tell me who it's intended for.",
        "/3.14/tutorial/",
        ("program", "python"),
    ),
    Site(
        "SQLite",
        "https://www.sqlite.org/docs.html",
        "Open the Getting Started guide and tell me the name of the command-line program it recommends.",
        "/quickstart.html",
        ("sqlite3",),
    ),
    Site(
        "W3C",
        "https://www.w3.org/WAI/fundamentals/accessibility-intro/",
        "Open Accessibility Principles and tell me the four principles it lists.",
        "/WAI/fundamentals/accessibility-principles/",
        ("perceivable", "operable", "understandable", "robust"),
    ),
)


def matched(url, site):
    observed = urlsplit(url)
    return observed.hostname == urlsplit(
        site.start
    ).hostname and observed.path.removesuffix("index.html").rstrip(
        "/"
    ) == site.destination.rstrip("/")


def trial(sites, live, limit):
    wire = WireLog(limit)
    if live:
        with existing_groq() as (key, model_name, usage):
            return run(sites, wire, key, model_name, usage)
    return run(sites, wire)


def run(sites, wire, key=None, model_name=None, usage=None):
    results = []
    sdk = None
    client = PlaywrightMCP(headless=True, mode="isolated")
    with tempfile.TemporaryDirectory(prefix="jarvis-public-trial-") as directory:
        root = Path(directory)
        app = build_application(
            JarvisSettings(workspace_dir=root, state_dir=root / "state")
        )
        browser = app.tool_service.registry.get("browser_mcp")
        browser.client = client
        app.tool_service.executor.policy.set_decision(
            Capability.USE_BROWSER, PermissionDecision.ALLOW
        )

        def turn(interact, prompt, source="text"):
            before = wire.calls, wire.tokens, len(wire.statuses)
            started = time.perf_counter()
            control = RequestControl(
                input_source=source, retry_budget=RetryBudget(limit=0)
            )
            reply = interact(prompt, request_control=control)
            return {
                "kind": reply.kind,
                "reply": reply.message,
                "source_evidence": reply.details.partition("\n\nSources read:\n")[2],
                "url": browser.last.get("url", ""),
                "requests": wire.calls - before[0],
                "tokens": wire.tokens - before[1],
                "http_statuses": wire.statuses[before[2] :],
                "seconds": round(time.perf_counter() - started, 3),
                "completed_navigation": [
                    e.url
                    for e in reply.events
                    if e.stage == "action_done"
                    and e.operation in {"follow_link", "navigate", "back"}
                ],
            }

        try:
            if key:

                async def account_usage(response):
                    wire.status(response)
                    await wire.async_usage(response)
                    if response.is_success:
                        usage.record(
                            "groq",
                            key,
                            response.json().get("usage", {}),
                            dict(response.headers),
                        )

                http = httpx.AsyncClient(
                    event_hooks={
                        "request": [wire.async_count],
                        "response": [account_usage],
                    },
                    limits=httpx.Limits(max_keepalive_connections=0),
                )
                sdk = AsyncGroq(
                    api_key=key, http_client=http, max_retries=0, timeout=15
                )
                settings = {"max_tokens": 400}
                if model_name.startswith("openai/gpt-oss-"):
                    settings["groq_reasoning_effort"] = "low"
                prototype = Prototype(
                    app,
                    GroqModel(
                        model_name,
                        provider=GroqProvider(groq_client=sdk),
                        settings=settings,
                    ),
                )

                def experimental(prompt, request_control):
                    return prototype.interact(prompt, request_control)

            for site in sites:
                app.new_conversation()
                opening = turn(app.interact, "Open " + site.start)
                row = {"site": site.name, "open": opening}
                results.append(row)
                if opening["kind"] != "action":
                    continue
                links = browser.last.get("links", [])
                row["observed_link_count"] = len(links)
                row["target_link_positions"] = [
                    i for i, link in enumerate(links, 1) if matched(link["url"], site)
                ]
                row["target_shortlisted"] = any(
                    matched(link["url"], site)
                    for link in page_context(browser.last, site.goal)["links"]
                )
                if not key:
                    continue
                outcome = turn(experimental, site.goal)
                evidence = page_context(browser.last, site.goal)["snapshot"].casefold()
                outcome["terms_in_page_context"] = all(
                    term in evidence for term in site.answer_terms
                )
                outcome["pass"] = (
                    outcome["kind"] == "action"
                    and matched(outcome["url"], site)
                    and any(
                        matched(url, site) for url in outcome["completed_navigation"]
                    )
                    and all(
                        term in outcome["reply"].casefold()
                        for term in site.answer_terms
                    )
                    and outcome["terms_in_page_context"]
                    and outcome["source_evidence"].startswith(outcome["url"] + "\n")
                    and all(
                        term in outcome["source_evidence"].casefold()
                        for term in site.answer_terms
                    )
                )
                if site.name == "Python":
                    answer = outcome["reply"].casefold()
                    outcome["pass"] = (
                        outcome["pass"]
                        and bool(
                            re.search(
                                r"\b(?:not\b.{0,45}\b(?:beginner|new to programming)|(?:basic|prior|existing|already|some)\b.{0,38}\bprogramming)",
                                answer,
                            )
                        )
                        and "and beginners" not in answer
                    )
                row["task"] = outcome
                if not outcome["pass"]:
                    continue
                if site.name == "Python":
                    followup = turn(
                        experimental,
                        "Would you point somebody who has never programmed to that tutorial first?",
                    )
                    answer = followup["reply"].lower()
                    followup["pass"] = (
                        followup["kind"] == "answer"
                        and "program" in answer
                        and (
                            re.search(r"\bno\b", answer)
                            or "wouldn't" in answer
                            or "would not" in answer
                        )
                        and followup["url"] == outcome["url"]
                        and followup["source_evidence"].startswith(
                            outcome["url"] + "\n"
                        )
                        and "programming" in followup["source_evidence"].casefold()
                        and not followup["completed_navigation"]
                    )
                    row["followup"] = followup
                back = turn(experimental, "No, wait, go back", source="voice")
                back["pass"] = (
                    back["kind"] == "action"
                    and back["url"] == opening["url"]
                    and back["requests"] == 0
                )
                row["back"] = back
            if client.thread:
                tabs = browser.execute({"action": "tabs"})["tabs"]
            else:
                tabs = ""
        finally:
            if sdk is not None:
                asyncio.run(sdk.close())
            app.shutdown()
    return {
        "model": model_name,
        "requests": wire.calls,
        "tokens": wire.tokens,
        "tabs": tabs,
        "browser_closed": client.thread is None,
        "sites": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--site", choices=[site.name for site in SITES])
    parser.add_argument("--limit", type=int, choices=range(1, 11), default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            trial(
                [site for site in SITES if not args.site or args.site == site.name],
                args.live,
                args.limit,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
