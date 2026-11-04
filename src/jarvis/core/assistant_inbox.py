"""Persistent review inbox for completed background work. No deployment authority."""

from dataclasses import asdict, dataclass, replace
from threading import RLock

from jarvis.agents.team import Job
from jarvis.core.personal_memory import PersonalMemory


@dataclass(frozen=True)
class AssistantUpdate:
    update_id: str
    job_id: str
    title: str
    body: str
    agent: str
    outcome: str
    created_at: float
    state: str = "new"


class AssistantInbox:
    def __init__(self, memory: PersonalMemory) -> None:
        self.memory = memory
        self._lock = RLock()

    def updates(self, *, include_dismissed: bool = False) -> list[AssistantUpdate]:
        with self._lock:
            rows = [AssistantUpdate(**r) for r in self.memory.records("assistant_update")]  # type: ignore[arg-type]
            return sorted((r for r in rows if include_dismissed or r.state != "dismissed"),
                          key=lambda r: r.created_at, reverse=True)

    def collect(self, jobs: tuple[Job, ...]) -> list[AssistantUpdate]:
        with self._lock:
            existing = {r.job_id for r in self.updates(include_dismissed=True)}
            created = []
            for job in jobs:
                if job.status not in {"completed", "failed", "interrupted"} or job.job_id in existing:
                    continue
                ready = job.status == "completed"
                update = AssistantUpdate(job.job_id, job.job_id,
                                         f"{job.agent}: draft ready for review" if ready else f"{job.agent}: task needs attention",
                                         job.result or "No result was returned. Check this task in Tasks.",
                                         job.agent, job.status, job.created_at)
                self.memory.save_record("assistant_update", update.update_id, asdict(update))
                existing.add(job.job_id)
                created.append(update)
            return created

    def unread_count(self) -> int:
        return sum(r.state == "new" for r in self.updates())

    def transition(self, update_id: str, state: str) -> None:
        if state not in {"reviewed", "dismissed"}:
            raise ValueError("Choose reviewed or dismissed; reviewing never applies a change.")
        with self._lock:
            update = next((r for r in self.updates(include_dismissed=True) if r.update_id == update_id), None)
            if update is None:
                raise ValueError("This update does not exist.")
            if update.state == "dismissed" and state != "dismissed":
                raise ValueError("A dismissed update cannot be reopened automatically.")
            self.memory.save_record("assistant_update", update_id, asdict(replace(update, state=state)))

    def quiet(self) -> bool:
        policy = self.memory.records("assistant_attention")
        return bool(policy and policy[0].get("quiet"))

    def set_quiet(self, quiet: bool) -> None:
        self.memory.save_record("assistant_attention", "main", {"quiet": quiet})
