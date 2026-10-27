"""Explicit chat controls, parsed locally before any model receives the request."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from jarvis.agents.team import WorkerDefinition

if TYPE_CHECKING:
    from jarvis.core.application import JarvisApplication


def assistant_command(app: JarvisApplication, prompt: str) -> str | None:
    text = prompt.strip()
    lowered = text.casefold().rstrip("?.!")
    if lowered in {"show memory", "what do you remember", "memory"}:
        facts = app.personal_memory.facts()
        return "\n".join(f"{k}: {v}" for k, v in facts.items()) or "No personal memories saved yet."
    if lowered == "clear memory":
        app.personal_memory.clear()
        app.conversation.clear()
        return "Personal memories and recent chat context cleared."
    match = re.fullmatch(r"remember(?: that)?\s+(.+)", text, re.IGNORECASE | re.DOTALL)
    if match:
        fact = match[1].strip()
        name, separator, value = fact.partition("=")
        if not separator:
            name, value = fact[:200], fact
        app.personal_memory.remember(name, value)
        return f"Remembered {name.strip()}: {value.strip()}"
    match = re.fullmatch(r"forget\s+(.+)", text, re.IGNORECASE)
    if match:
        removed = app.personal_memory.forget(match[1].strip())
        # Discard an old prompt that may still contain the forgotten preference.
        app.conversation.clear()
        return "Memory removed." if removed else "No memory with that exact name. Use 'show memory'."
    if lowered in {"agents", "list agents"}:
        return "\n".join(f"{a.name} → {a.backend}" for a in app.agent_team.agents())
    match = re.fullmatch(r"assign\s+([\w-]+)\s+to\s+(local|chatgpt|hermes)", text, re.IGNORECASE)
    if match:
        backend = match[2].casefold()
        if backend not in {"local", "chatgpt", "hermes"}:
            return None
        app.agent_team.configure(WorkerDefinition(match[1], backend))  # type: ignore[arg-type]
        return f"Agent {match[1]} now uses {backend}. Delegate with: delegate to {match[1]}: your task"
    match = re.fullmatch(r"(?:delegate to|ask agent)\s+([\w-]+)\s*:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if match:
        job = app.agent_team.submit(match[1], match[2])
        return f"Assigned task {job.job_id} to {job.agent}. Track it in Tasks or type 'task {job.job_id}'."
    if lowered.startswith("parallel:"):
        parts = text.split(":", 1)[1].split("||")
        if not 2 <= len(parts) <= 10:
            raise ValueError("Use parallel: agent: task || agent: task (2–10 tasks).")
        assignments = []
        known = {a.name for a in app.agent_team.agents()}
        for part in parts:
            name, separator, task = part.strip().partition(":")
            if not separator or name.strip().casefold() not in known or not task.strip() or len(task) > 20000:
                raise ValueError("Each parallel assignment needs a known agent and a nonempty task.")
            assignments.append((name.strip(), task.strip()))
        jobs = app.agent_team.submit_many(assignments)
        return "\n".join(f"{j.job_id}: assigned to {j.agent}" for j in jobs)
    if lowered in {"tasks", "list tasks"}:
        return "\n".join(f"{j.job_id} | {j.agent} | {j.status}" for j in app.agent_team.jobs()[:20]) or "No tasks yet."
    match = re.fullmatch(r"task\s+([a-f0-9]{12})", text, re.IGNORECASE)
    if match:
        job = app.agent_team.job(match[1].lower())
        return f"{job.agent} | {job.status}\n{job.result or 'Work has not finished yet.'}"
    match = re.fullmatch(r"cancel task\s+([a-f0-9]{12})", text, re.IGNORECASE)
    if match:
        return ("Queued task cancelled." if app.agent_team.cancel(match[1].lower())
                else "This task is already running or finished. Running requests use the provider timeout.")
    return None
