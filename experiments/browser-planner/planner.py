"""Experimental decision path using Jarvis's existing action gateway."""

import asyncio
import json
from dataclasses import replace

from jarvis.core.interaction import AssistantEvent, build_reply, short_reply
from jarvis.core.navigation_reference import page_navigation
from jarvis.core.request_control import (
    RequestCancelledError,
    check_cancelled,
    report_event,
    request_scope,
)
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import ModelMessage
from jarvis.models.connection_errors import ProviderConnectionError
from jarvis.agents.grounded_browser import Decision, INSTRUCTIONS, page_context, page_decision_type
from pydantic_ai import Agent, NativeOutput, UsageLimits
from pydantic_ai.exceptions import UnexpectedModelBehavior


class Prototype:
    def __init__(self, app, model):
        self.app = app
        self.agent = Agent(
            model,
            output_type=NativeOutput(Decision, strict=True),
            instructions=INSTRUCTIONS,
            retries=0,
        )

    async def _decide(self, data, control, source_count):
        decision_type = page_decision_type(source_count)
        task = asyncio.create_task(
            self.agent.run(
                json.dumps(data),
                output_type=NativeOutput(decision_type, strict=True),
                usage_limits=UsageLimits(request_limit=1),
                timeout=15,
            )
        )
        try:
            while not task.done():
                if control.cancelled.is_set():
                    raise RequestCancelledError(
                        "Stopped before executing another action."
                    )
                await asyncio.wait({task}, timeout=0.05)
            try:
                return task.result().output
            except UnexpectedModelBehavior as error:
                raise ValueError(
                    "I couldn't verify the planner's decision for this page."
                ) from error
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    def interact(self, prompt, control):
        app = self.app
        if app.fast_command_router.route(prompt) or page_navigation(prompt):
            return app.interact(prompt, request_control=control)

        browser = app.tool_service.registry.get("browser_mcp")
        history = [
            {"role": m.role, "text": m.content[:500]}
            for m in app.conversation.snapshot()[-6:]
        ]
        steps = []
        try:
            with request_scope(control):
                report_event(AssistantEvent("thinking", "I'm on it."))
                page = (
                    browser.last
                    if browser.last.get("url") == app.interaction.focus_url
                    else {}
                )
                for _ in range(2):
                    context = page_context(page, prompt)
                    link_fields = ("links", "result_links")
                    model_page = dict(context)
                    source_lines = context["snapshot"].splitlines()
                    model_page["snapshot"] = "\n".join(
                        f"[{index}] {line}"
                        for index, line in enumerate(source_lines, 1)
                    )
                    for field in link_fields:
                        model_page[field] = (
                            []
                            if steps
                            else [
                                {"index": link["index"], "label": link["label"][:120]}
                                for link in context[field]
                            ]
                        )
                    data = {
                        "request": prompt,
                        "recent_conversation": history,
                        "completed_steps": steps,
                        "phase": "The destination is open. Answer from this page or clarify. Do not navigate."
                        if steps
                        else "Answer from the current page or propose one navigation.",
                        "page": model_page,
                    }
                    decision = asyncio.run(
                        self._decide(data, control, len(source_lines))
                    )
                    check_cancelled()
                    if decision.kind in {"reply", "clarify"}:
                        if not decision.text.strip():
                            raise ValueError("The planner returned an empty reply.")
                        if decision.kind == "clarify":
                            control.events.append(
                                AssistantEvent("clarification", decision.text)
                            )
                        evidence = list(dict.fromkeys(decision.evidence))
                        if any(
                            not 1 <= index <= len(source_lines) for index in evidence
                        ):
                            raise ValueError(
                                "I couldn't verify the quoted evidence on the page."
                            )
                        quotes = [source_lines[index - 1] for index in evidence]
                        if steps and decision.kind == "reply" and not quotes:
                            raise ValueError(
                                "I opened the page but couldn't verify the answer from it."
                            )
                        details = decision.text
                        if quotes:
                            details += (
                                "\n\nSources read:\n"
                                + page["url"]
                                + "\n"
                                + "\n".join(quotes)
                            )
                        reply = build_reply(details, control.events)
                        if quotes:
                            reply = replace(
                                reply,
                                message=decision.text,
                                spoken_text=short_reply(
                                    decision.text, sentence_limit=0
                                ),
                            )
                        break
                    if steps:
                        raise ValueError(
                            "I opened the destination but couldn't complete the answer from it."
                        )
                    kind = "result" if decision.kind == "open_result" else "link"
                    links = context["result_links" if kind == "result" else "links"]
                    selected = next(
                        (link for link in links if link["index"] == decision.index),
                        None,
                    )
                    if selected is None:
                        raise ValueError(
                            "The proposed link is not in the observed page."
                        )
                    target = selected["url"]
                    if target == page.get("url") or any(
                        step["target"] == target for step in steps
                    ):
                        raise ValueError("The planner tried to repeat a navigation.")
                    page = app._execute_tool_with_confirmation(
                        ToolRequest(
                            tool_name="browser_mcp",
                            arguments={
                                "action": "follow_link",
                                "link_kind": kind,
                                "link_index": decision.index,
                            },
                        ),
                        None,
                    )
                    steps.append({"target": target, "observed_url": page["url"]})
                else:
                    raise ValueError("The planner reached its two-decision limit.")
        except ProviderConnectionError as error:
            reply = build_reply(str(error), control.events, error=error)
        except Exception as error:  # noqa: BLE001 -- keep the trial result when the provider or tool fails
            status = getattr(error, "status_code", None)
            if status is not None:
                error = ProviderConnectionError(
                    f"Groq returned HTTP {status}.", status_code=status
                )
            reply = build_reply(
                str(error)
                if isinstance(
                    error, (ValueError, RequestCancelledError, ProviderConnectionError)
                )
                else type(error).__name__,
                control.events,
                error=error,
            )
        app.interaction.record(reply)
        app.conversation.replace(
            (
                app.conversation.snapshot()
                + [
                    ModelMessage(role="user", content=prompt),
                    ModelMessage(role="assistant", content=reply.message),
                ]
            )[-40:]
        )
        return reply
