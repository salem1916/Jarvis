from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from jarvis.agents.team import Job
from jarvis.core.assistant_inbox import AssistantInbox
from jarvis.core.personal_memory import PersonalMemory


def completed(job_id="job1", status="completed"):
    return Job(job_id, "designer", "local", "Draft ideas", status, "A draft, not a deployed change", created_at=1)


def test_terminal_jobs_only_and_repeated_polls_do_not_duplicate():
    inbox = AssistantInbox(PersonalMemory())
    assert not inbox.collect((completed(status="running"),))
    assert len(inbox.collect((completed(),))) == 1
    assert not inbox.collect((completed(),))
    assert inbox.unread_count() == 1
    assert inbox.updates()[0].outcome == "completed"


def test_review_dismiss_and_quiet_survive_restart(tmp_path: Path):
    path = tmp_path / "state.sqlite3"
    memory = PersonalMemory(path)
    inbox = AssistantInbox(memory)
    inbox.collect((completed(), completed("job2", "failed")))
    inbox.transition("job1", "reviewed")
    inbox.transition("job2", "dismissed")
    inbox.set_quiet(True)
    memory.close()
    memory = PersonalMemory(path)
    inbox = AssistantInbox(memory)
    assert inbox.unread_count() == 0 and inbox.quiet()
    assert len(inbox.updates()) == 1
    assert not inbox.collect((completed(), completed("job2", "failed")))
    with pytest.raises(ValueError):
        inbox.transition("job1", "applied")
    with pytest.raises(ValueError):
        inbox.transition("job2", "reviewed")
    memory.close()


def test_concurrent_collectors_do_not_create_duplicate_notifications():
    inbox = AssistantInbox(PersonalMemory())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: inbox.collect((completed(),)), range(12)))
    assert sum(len(r) for r in results) == 1


def test_failed_and_interrupted_jobs_are_attention_items_not_success_claims():
    inbox = AssistantInbox(PersonalMemory())
    updates = inbox.collect((completed(status="failed"), completed("job2", "interrupted")))
    assert all("needs attention" in u.title for u in updates)


def test_actual_background_job_becomes_an_update_after_completion():
    from threading import Event

    from jarvis.agents.team import AgentTeam

    memory = PersonalMemory()
    entered, release = Event(), Event()
    def worker(agent, prompt):
        entered.set()
        assert release.wait(3)
        return "Prepared a draft for review"
    team = AgentTeam(memory, worker)
    inbox = AssistantInbox(memory)
    job = team.submit("local", "Draft a website improvement proposal")
    try:
        assert entered.wait(2)
        assert not inbox.collect(team.jobs())
        release.set()
        team._futures[job.job_id].result(timeout=3)
        assert len(inbox.collect(team.jobs())) == 1
        assert inbox.updates()[0].body == "Prepared a draft for review"
        inbox.transition(job.job_id, "reviewed")
        assert team.job(job.job_id).status == "completed"
    finally:
        release.set()
        team.shutdown()
        memory.close()
