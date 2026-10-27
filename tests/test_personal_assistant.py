import json
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

import httpx
import pytest

from jarvis.agents.hermes import HermesAgentEngine
from jarvis.agents.team import AgentTeam, WorkerDefinition
from jarvis.bootstrap import build_application, build_model_manager
from jarvis.core.application import JarvisApplication
from jarvis.core.config import JarvisSettings
from jarvis.core.conversation import Conversation
from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_router import RequestRouter, RouteTarget
from jarvis.models.base import ModelProvider, ModelRequest, ModelResponse
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.runtime.profile import AgentEngineId, ModelRole, RuntimeMode, RuntimeProfile


class RecordingProvider(ModelProvider):
    name = "recording"
    model = "test-model"

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(text="Here is an explanation.", provider=self.name, model=self.model)


def make_app(tmp_path: Path) -> JarvisApplication:
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.cloud_provider = RecordingProvider()
    app.local_worker_provider = RecordingProvider()
    return app


def test_memory_survives_restart_and_can_be_forgotten(tmp_path: Path) -> None:
    path = tmp_path / "memory.sqlite3"
    memory = PersonalMemory(path)
    memory.remember("learning_goal", "Spring Boot and SQL")
    memory.remember_turn("Help with SQL", "Use a join")
    memory.close()
    memory = PersonalMemory(path)
    assert memory.facts() == {"learning_goal": "Spring Boot and SQL"}
    assert "Spring Boot" in memory.context("Help me learn", include_recent=True)
    assert "Use a join" in memory.context("Help me learn", include_recent=True)
    assert memory.forget("learning_goal")
    assert not memory.facts()
    assert not memory.recent_turns()
    memory.close()


def test_memory_recent_context_is_bounded() -> None:
    memory = PersonalMemory()
    for index in range(40):
        memory.remember_turn(str(index), "x" * 10000)
    assert len(memory.recent_turns()) == 12
    assert len(memory.context("hello", include_recent=True)) < 7000
    memory.clear()
    assert memory.context("hello", include_recent=True) == ""
    memory.close()


def test_team_really_runs_concurrently_and_keeps_assignment_snapshot() -> None:
    barrier = Barrier(3)
    release = Event()
    seen: list[tuple[str, str]] = []

    def run(worker: WorkerDefinition, prompt: str) -> str:
        seen.append((worker.backend, prompt))
        barrier.wait(timeout=3)
        assert release.wait(3)
        return prompt.upper()

    memory = PersonalMemory()
    team = AgentTeam(memory, run)
    team.configure(WorkerDefinition("coder", "chatgpt", "Explain Java"))
    jobs = team.submit_many([("coder", "java"), ("local", "sql")])
    try:
        barrier.wait(timeout=3)  # Both workers must start before either can finish.
        assert all(j.status == "running" for j in team.jobs())
        team.configure(WorkerDefinition("coder", "local"))
        assert ("chatgpt", "java") in seen
        assert ("local", "sql") in seen
    finally:
        release.set()
        team.shutdown()
    assert {j.result for j in team.jobs()} == {"JAVA", "SQL"}
    assert all(j.status == "completed" for j in team.jobs())
    assert team.job(jobs[0].job_id).backend == "chatgpt"
    memory.close()


def test_job_persistence_failure_and_restart_interruption(tmp_path: Path) -> None:
    path = tmp_path / "memory.sqlite3"
    memory = PersonalMemory(path)

    def fail(worker: WorkerDefinition, prompt: str) -> str:
        raise RuntimeError("Bearer secret-token should never be saved")

    team = AgentTeam(memory, fail)
    team.configure(WorkerDefinition("coder", "chatgpt"))
    job = team.submit("coder", "Explain Java")
    team._futures[job.job_id].result(timeout=3)
    team.shutdown()
    assert team.job(job.job_id).status == "failed"
    assert "secret-token" not in team.job(job.job_id).result
    memory.save_record("job", "unfinished", {
        "job_id": "unfinished", "agent": "coder", "backend": "chatgpt",
        "prompt": "unfinished task", "status": "running", "created_at": 1,
    })
    memory.close()
    memory = PersonalMemory(path)
    team = AgentTeam(memory, fail)
    assert team.job(job.job_id).status == "failed"
    assert team.job("unfinished").status == "interrupted"
    assert any(a.name == "coder" for a in team.agents())
    team.shutdown()
    memory.close()


def test_queue_cancel_and_batch_validation_are_atomic() -> None:
    entered, release = Event(), Event()

    def run(worker: WorkerDefinition, prompt: str) -> str:
        entered.set()
        assert release.wait(3)
        return prompt

    memory = PersonalMemory()
    team = AgentTeam(memory, run, max_workers=1, max_pending=2)
    first = team.submit("local", "first")
    try:
        assert entered.wait(2)
        queued = team.submit("local", "queued")
        assert team.cancel(queued.job_id)
        assert not team.cancel(first.job_id)
        with pytest.raises(ValueError, match="space"):
            team.submit_many([("local", "one"), ("local", "two")])
        assert len(team.jobs()) == 2
    finally:
        release.set()
        team.shutdown()
    assert team.job(queued.job_id).status == "cancelled"
    memory.close()


def test_chat_memory_commands_and_updates_reach_model(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    cloud = app.cloud_provider
    assert isinstance(cloud, RecordingProvider)
    assert "Remembered" in app.ask_with_tools("remember learning_goal = Spring Boot")
    app.ask_with_tools("Explain dependency injection")
    assert "Spring Boot" in str(cloud.requests[-1])
    app.ask_with_tools("remember learning_goal = SQL")
    app.ask_with_tools("Explain joins")
    assert "SQL" in cloud.requests[-1].messages[0].content
    assert "Spring Boot" not in cloud.requests[-1].messages[0].content
    assert "SQL" in app.ask_with_tools("show memory")
    assert app.last_route_decision() is None
    assert "removed" in app.ask_with_tools("forget learning_goal")
    assert not app.personal_memory.facts()
    app.shutdown()


def test_direct_api_route_and_explicit_local_override(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    cloud = app.cloud_provider
    local = app.local_worker_provider
    assert isinstance(cloud, RecordingProvider) and isinstance(local, RecordingProvider)
    app.ask_with_tools("Explain relational databases")
    assert len(cloud.requests) == 1
    assert len(local.requests) == 0
    decision = app.last_route_decision()
    assert decision is not None and decision.target == RouteTarget.OPENAI
    telemetry = app.last_execution_telemetry()
    assert telemetry is not None and "test-model" in (telemetry.model or "")
    app.ask_with_tools("@local Explain SQL")
    assert len(local.requests) == 1
    app.shutdown()


def test_local_mode_cannot_call_cloud_even_when_main_is_cloud(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    cloud = app.cloud_provider
    assert app.model_manager is not None
    app.model_manager.set_mode(RuntimeMode.LOCAL)
    app.ask_with_tools("Explain SQL")
    assert isinstance(cloud, RecordingProvider) and not cloud.requests
    with pytest.raises(ValueError, match="Local mode"):
        app.ask_with_tools("@chatgpt Explain SQL")
    with pytest.raises(ValueError, match="Local mode"):
        app._run_independent_worker(WorkerDefinition("coder", "chatgpt"), "SQL")
    app.shutdown()


def test_workers_are_isolated_and_receive_no_pc_tools(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.personal_memory.remember("style", "Use examples")
    app.ask_with_tools("Explain SQL")
    count = len(app.conversation)
    provider = app.cloud_provider
    assert isinstance(provider, RecordingProvider)
    app._run_independent_worker(WorkerDefinition("coder", "chatgpt", "Teach Java"), "Explain classes")
    request = provider.requests[-1]
    assert not request.tools and not request.messages
    assert "Use examples" in (request.system_prompt or "")
    assert "Teach Java" in (request.system_prompt or "")
    assert len(app.conversation) == count
    app.shutdown()


def test_missing_key_is_actionable_and_never_falls_back_silently(tmp_path: Path) -> None:
    app = build_application(JarvisSettings(workspace_dir=tmp_path, openai_api_key=None))
    with pytest.raises(ValueError, match="JARVIS_OPENAI_API_KEY"):
        app.ask_with_tools("@chatgpt Explain SQL")
    app.shutdown()


def test_chat_assignments_and_parallel_invalid_batch(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.ask_with_tools("assign coder to chatgpt")
    assert "coder" in app.ask_with_tools("list agents")
    before = len(app.agent_team.jobs())
    with pytest.raises(ValueError, match="known agent"):
        app.ask_with_tools("parallel: coder: explain Java || missing: explain SQL")
    assert len(app.agent_team.jobs()) == before
    response = app.ask_with_tools("parallel: coder: explain Java || local: explain SQL")
    assert "assigned to coder" in response
    assert "assigned to local" in response
    app.agent_team.shutdown()
    assert all(j.status in {"completed", "cancelled"} for j in app.agent_team.jobs())
    app.personal_memory.close()


def test_openai_provider_is_registered_without_network(tmp_path: Path) -> None:
    settings = JarvisSettings(workspace_dir=tmp_path, openai_api_key="test-key", openai_model="configured-model")
    manager = build_model_manager(settings)
    manager.set_model(ModelRole.MAIN, "openai", "configured-model")
    provider = manager.build_provider(ModelRole.MAIN)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "configured-model"


def test_local_hermes_never_uses_the_cloud_main_endpoint(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.model_provider = OpenAICompatibleProvider(
        provider_name="openai", model="test", base_url="https://api.openai.com/v1", api_key="test"
    )
    engine = app._build_local_hermes_engine()
    assert engine.base_url == "http://127.0.0.1:11434/v1"
    app.shutdown()


@pytest.mark.parametrize("mode", list(RuntimeMode))
def test_direct_cloud_router_respects_modes(mode: RuntimeMode) -> None:
    route = RequestRouter().route("Explain SQL", RuntimeProfile(mode=mode), direct_cloud_available=True)
    assert route.target == (RouteTarget.NATIVE if mode == RuntimeMode.LOCAL else RouteTarget.OPENAI)


def test_explicit_engine_overrides_are_preserved() -> None:
    route = RequestRouter().route("Explain SQL", RuntimeProfile(agent_engine=AgentEngineId.HERMES),
                                  direct_cloud_available=True)
    assert route.target == RouteTarget.HERMES


def test_openai_request_contract_uses_configured_model_and_memory(tmp_path: Path) -> None:
    sent = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": "SQL explanation"}}]})

    app = make_app(tmp_path)
    app.cloud_provider = OpenAICompatibleProvider(
        provider_name="openai", model="configured-model", base_url="https://api.openai.com/v1",
        api_key="test-key", transport=httpx.MockTransport(handle),
    )
    app.ask_with_tools("remember style = short answers")
    assert app.ask_with_tools("Explain SQL") == "SQL explanation"
    assert sent[0]["model"] == "configured-model"
    assert "short answers" in str(sent[0]["messages"])
    assert "test-key" not in str(app.personal_memory.recent_turns())
    app.shutdown()


def test_hermes_success_updates_conversation_and_failure_preserves_it() -> None:
    conversation = Conversation()
    engine = HermesAgentEngine()
    with patch.object(engine, "_run_once", return_value="first answer"):
        engine.run("first question", conversation=conversation)
    assert len(conversation) == 2
    with patch.object(engine, "_run_once", side_effect=RuntimeError("failed")), pytest.raises(RuntimeError):
        engine.run("second question", conversation=conversation)
    assert len(conversation) == 2


def test_polite_app_launch_skips_models_and_uses_trusted_executor(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    provider = app.cloud_provider
    with patch.object(app, "_execute_tool_with_confirmation", return_value={"application": "Notepad"}) as execute:
        assert app.ask_with_tools("Could you please open notepad?") == "Opened Notepad."
    request = execute.call_args.kwargs["request"]
    assert request.tool_name == "open_application"
    assert isinstance(provider, RecordingProvider) and not provider.requests
    assert app.last_route_decision() is None
    app.shutdown()
