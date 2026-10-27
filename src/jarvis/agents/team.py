"""Bounded parallel workers with isolated conversations and durable job results."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from threading import RLock
from typing import Literal
from uuid import uuid4

from jarvis.core.personal_memory import PersonalMemory

Backend = Literal["local", "chatgpt", "hermes"]


@dataclass(frozen=True)
class WorkerDefinition:
    name: str
    backend: Backend
    instructions: str = ""
    model: str = ""


@dataclass(frozen=True)
class Job:
    job_id: str
    agent: str
    backend: str
    prompt: str
    status: str = "queued"
    result: str = ""
    created_at: float = 0
    duration: float = 0


class AgentTeam:
    def __init__(self, memory: PersonalMemory,
                 run_worker: Callable[[WorkerDefinition, str], str],
                 max_workers: int = 3, max_pending: int = 30) -> None:
        self.memory = memory
        self._run_worker = run_worker
        self._lock = RLock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="jarvis-agent")
        self._max_pending = max_pending
        self._closed = False
        self._agents = {
            "local": WorkerDefinition("local", "local"),
            "chatgpt": WorkerDefinition("chatgpt", "chatgpt"),
            "hermes": WorkerDefinition("hermes", "hermes"),
        }
        for raw in memory.records("agent"):
            self._agents[str(raw["name"])] = WorkerDefinition(**raw)  # type: ignore[arg-type]
        self._jobs: dict[str, Job] = {}
        self._futures: dict[str, Future[None]] = {}
        for raw in memory.records("job"):
            job = Job(**raw)  # type: ignore[arg-type]
            if job.status in {"queued", "running"}:
                job = replace(job, status="interrupted", result="Application stopped before completion. Reassign to retry.")
                memory.save_record("job", job.job_id, asdict(job))
            self._jobs[job.job_id] = job

    def agents(self) -> tuple[WorkerDefinition, ...]:
        with self._lock:
            return tuple(self._agents.values())

    def configure(self, agent: WorkerDefinition) -> None:
        name = agent.name.strip().casefold()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name):
            raise ValueError("Agent names must start with a letter and use up to 40 letters, numbers, _ or -.")
        if agent.backend not in {"local", "chatgpt", "hermes"}:
            raise ValueError("Choose local, chatgpt, or hermes.")
        if agent.backend == "hermes" and agent.model:
            raise ValueError("Configure the Hermes model in Hermes itself; leave the override empty.")
        agent = replace(agent, name=name)
        with self._lock:
            self.memory.save_record("agent", name, asdict(agent))
            self._agents[name] = agent

    def submit(self, agent_name: str, prompt: str) -> Job:
        if not prompt.strip() or len(prompt) > 20000:
            raise ValueError("Enter a task of 1–20000 characters.")
        with self._lock:
            if self._closed:
                raise RuntimeError("The agent team has shut down.")
            agent = self._agents.get(agent_name.strip().casefold())
            if agent is None:
                raise ValueError(f"Unknown agent: {agent_name}. Configure it in Tasks first.")
            if sum(j.status in {"queued", "running"} for j in self._jobs.values()) >= self._max_pending:
                raise ValueError("The task queue is full. Wait for jobs to finish or cancel queued jobs.")
            job = Job(uuid4().hex[:12], agent.name, agent.backend, prompt.strip(), created_at=time.time())
            self._save(job)
            self._futures[job.job_id] = self._pool.submit(self._execute, job.job_id, agent)
            return job

    def _save(self, job: Job) -> None:
        self.memory.save_record("job", job.job_id, asdict(job))
        self._jobs[job.job_id] = job

    def submit_many(self, assignments: list[tuple[str, str]]) -> list[Job]:
        with self._lock:
            if self._closed:
                raise RuntimeError("The agent team has shut down.")
            pending = sum(j.status in {"queued", "running"} for j in self._jobs.values())
            if pending + len(assignments) > self._max_pending:
                raise ValueError("Not enough space in the task queue for this batch.")
            for name, prompt in assignments:
                if name.strip().casefold() not in self._agents or not prompt.strip() or len(prompt) > 20000:
                    raise ValueError("Each assignment needs a known agent and a valid task.")
            return [self.submit(name, prompt) for name, prompt in assignments]

    def _execute(self, job_id: str, agent: WorkerDefinition) -> None:
        started = time.perf_counter()
        with self._lock:
            job = replace(self._jobs[job_id], status="running")
            self._save(job)
        try:
            answer = self._run_worker(agent, job.prompt)
            status = "completed"
        except Exception as exc:  # noqa: BLE001 -- failed workers must not break the queue
            # Do not persist HTTP headers, credentials, or arbitrary subprocess output.
            answer = (str(exc) if isinstance(exc, (ValueError, LookupError))
                      else "The worker failed. Check the provider connection, model, or Hermes installation and retry.")
            status = "failed"
        with self._lock:
            self._save(replace(job, status=status, result=answer,
                               duration=time.perf_counter() - started))

    def jobs(self) -> tuple[Job, ...]:
        with self._lock:
            return tuple(sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True))

    def job(self, job_id: str) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                raise ValueError(f"Unknown task: {job_id}")
            return self._jobs[job_id]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self.job(job_id)
            future = self._futures.get(job_id)
            if future is None or not future.cancel():
                return False
            self._save(replace(job, status="cancelled"))
            return True

    def has_active_jobs(self) -> bool:
        return any(j.status in {"queued", "running"} for j in self.jobs())

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for job in self.jobs():
                if job.status == "queued":
                    self.cancel(job.job_id)
        self._pool.shutdown(wait=True, cancel_futures=True)
