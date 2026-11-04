import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from jarvis.agents.reasoning import ReasoningAgentEngine
from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.conversation import Conversation
from jarvis.core.fast_command_router import FastCommandRouter
from jarvis.core.system_prompt import build_system_prompt
from jarvis.models.base import ModelMessage, ModelProvider, ModelResponse
from jarvis.runtime.profile import RuntimeMode
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision


class Model(ModelProvider):
    name = "test"
    model = "test"
    def __init__(self):
        self.requests = []
        self.replies = []
    def generate(self, request):
        self.requests.append(request)
        response = self.replies.pop(0) if self.replies else "An ordinary helpful answer."
        if isinstance(response, Exception):
            raise response
        return ModelResponse(text=json.dumps(response) if isinstance(response, dict) else response,
                             provider=self.name, model=self.model)


def plan(query, source=1, engine="youtube", **extra):
    return {"intent":"search", "query":query, "engine":engine, "source_turns":[source], "confidence":"high", **extra}


@pytest.fixture
def assistant(tmp_path: Path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    model, opened = Model(), []
    app.cloud_provider = model
    app.local_worker_provider = model
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", lambda url: opened.append(url) or True)
    try:
        yield app, model, opened
    finally:
        app.shutdown()


def query(url):
    parsed = urlsplit(url)
    values = parse_qs(parsed.query)
    return parsed.hostname, values["search_query"][0] if "search_query" in values else values["q"][0]


@pytest.mark.parametrize("topic,search", [
    ("fastest way to make money and maybe show me a vd", "ways to earn money quickly"),
    ("How do I fix my laptop fan?", "laptop fan repair"),
    ("I want to understand SQL joins", "SQL joins explained"),
    ("How can I bake sourdough?", "sourdough baking for beginners"),
])
def test_reference_uses_earlier_user_goal_even_after_an_unhelpful_answer(assistant, topic, search):
    app, model, opened = assistant
    app.conversation.replace([ModelMessage(role="user", content=topic),
        ModelMessage(role="assistant", content="I cannot help. What video topic did you mean?")])
    model.replies = [plan(search)]
    reply = app.interact("search for a video that i asked for")
    assert reply.kind == "action" and query(opened[0]) == ("www.youtube.com", search)
    assert search in reply.message and "Youtube" in reply.message
    data = json.loads(model.requests[0].prompt)
    assert data["user_turns"] == [{"id":1, "text":topic}]
    assert "What video topic" not in model.requests[0].prompt
    assert len(model.requests) == 1


def test_exact_initial_compound_request_answers_and_opens_videos(assistant, monkeypatch):
    app, model, opened = assistant
    original = "fastest way to make money and maybe show me a vd"
    model.replies = [plan("ways to earn money quickly", source=0, answer_request="What are practical ways to earn money quickly?"),
                     "Selling unused items and taking short paid work can provide income; outcomes vary."]
    monkeypatch.setattr("jarvis.core.application.validated_sources", lambda *args: ([{
        "title":"Observed work guide", "url":"https://example.com/work", "text":"Evidence about ordinary paid work.",
        "retrieved_at":"2026-11-02T12:00:00Z"}], []))
    reply = app.interact(original, build_system_prompt(app.tool_service.registry))
    assert reply.kind == "action" and "paid work" in reply.message
    assert query(opened[0]) == ("www.youtube.com", "ways to earn money quickly")
    assert len(model.requests) == 2
    app.set_runtime_mode(RuntimeMode.SMART)
    followup = app.interact("search for a video that i asked for")
    assert followup.kind == "action" and len(model.requests) == 2
    assert query(opened[1]) == query(opened[0])


@pytest.mark.parametrize("prompt,engine,topic", [
    ("search for a video about Python decorators", "www.youtube.com", "Python decorators"),
    ("show me a video on building a desk", "www.youtube.com", "building a desk"),
    ("find a tutorial about SQL indexes", "www.youtube.com", "SQL indexes"),
    ("search youtube for C++ & C#", "www.youtube.com", "C++ & C#"),
    ("search for Java salaries on Google", "www.google.com", "Java salaries"),
])
def test_complete_searches_do_not_need_a_model(assistant, prompt, engine, topic):
    app, model, opened = assistant
    reply = app.interact(prompt)
    assert reply.kind == "action" and query(opened[0]) == (engine, topic)
    assert not model.requests and topic in reply.message


def test_missing_topic_clarifies_then_uses_the_answer(assistant):
    app, model, opened = assistant
    assert app.interact("show me a video").kind == "clarification"
    assert app.interact("yes").kind == "clarification"
    assert not opened and not model.requests
    reply = app.interact("Python decorators")
    assert reply.kind == "action" and query(opened[0]) == ("www.youtube.com", "Python decorators")
    assert not model.requests


def test_format_constraints_are_resolved_instead_of_dropped(assistant):
    app, model, opened = assistant
    app.interact("search youtube for Java streams")
    model.replies = [plan("Java streams German tutorial under 10 minutes", source=0, source_turns=[0,1])]
    app.interact("search for a video in German under 10 minutes")
    assert query(opened[-1])[1] == "Java streams German tutorial under 10 minutes"
    assert len(model.requests) == 1
    assert "Java streams" in model.requests[0].prompt


def test_a_new_topic_does_not_reuse_a_stale_cached_search(assistant):
    app, model, opened = assistant
    app.interact("search youtube for Java streams")
    app.interact("How do I bake sourdough?")
    model.replies = [plan("sourdough baking tutorial", source=2)]
    app.interact("find a video about that")
    assert query(opened[-1])[1] == "sourdough baking tutorial" and len(model.requests) == 2


@pytest.mark.parametrize("value", [
    {"intent":"execute", "tool":"run_shell"},
    plan("the video that I asked for"),
    plan("unrelated", source=99),
    plan("unrelated", source=True),
    plan("unrelated", confidence="low"),
    {**plan("unrelated"), "engine":["youtube"]},
    "Not JSON",
])
def test_unusable_plans_never_become_a_literal_or_invented_search(assistant, value):
    app, model, opened = assistant
    app.conversation.replace([ModelMessage(role="user", content="Explain sourdough starter")])
    model.replies = [value]
    reply = app.interact("search for a video that I asked for")
    assert reply.kind == "clarification" and not opened


def test_ambiguity_returns_the_focused_question_without_navigation(assistant):
    app, model, opened = assistant
    app.conversation.replace([ModelMessage(role="user", content="Find videos about Java and sourdough")])
    model.replies = [{"intent":"clarify", "question":"Do you mean Java or sourdough?"}]
    assert app.interact("search for the one I mentioned earlier").message == "Do you mean Java or sourdough?"
    assert not opened


def test_literal_fast_router_rejects_unresolved_search_references():
    router = FastCommandRouter()
    for prompt in ("search for a video that I asked for", "search for it", "search for a video", "search for the topic from before"):
        assert router.route(prompt) is None


def test_permission_denial_happens_before_context_is_sent_to_a_model(assistant):
    app, model, opened = assistant
    app.conversation.replace([ModelMessage(role="user", content="Explain Python decorators")])
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.DENY)
    assert app.interact("search for a video that I asked for").kind == "failed"
    assert not model.requests and not opened


def test_failed_understanding_retries_the_same_goal_without_a_literal_search(assistant):
    app, model, opened = assistant
    class NeverUseCloud(Model):
        def generate(self, request):
            pytest.fail("An explicit local understanding request used a cloud provider")
    app.cloud_provider = NeverUseCloud()
    app.conversation.replace([ModelMessage(role="user", content="Explain Python decorators")])
    model.replies = [RuntimeError("Temporarily unavailable"), plan("Python decorators tutorial")]
    assert app.interact("@local search for a video that I asked for").kind == "failed"
    assert not opened
    assert app.interact("try again").kind == "action"
    assert query(opened[0]) == ("www.youtube.com", "Python decorators tutorial")
    assert len(model.requests) == 2


def test_reasoning_keeps_assistant_behavior_without_the_action_catalog(assistant):
    app, model, _ = assistant
    system = build_system_prompt(app.tool_service.registry) + (
        "\n[JARVIS ASSISTANT BEHAVIOR]\nProvide practical help for ordinary lawful requests. "
        'Current context: {"last_search_topic":"Python decorators"}'
        "\n[JARVIS PERSONAL CONTEXT]\nA saved preference")
    ReasoningAgentEngine(model).run("Explain the topic", system, Conversation())
    sent = model.requests[0].messages[0].content
    assert "JARVIS ASSISTANT BEHAVIOR" in sent and "Python decorators" in sent
    assert "ordinary lawful" in sent and "A saved preference" in sent
    assert "JARVIS currently provides these REAL tools" not in sent
    assert "No action tools are attached" not in sent


def test_hermes_intent_reader_has_no_action_bridge(assistant, monkeypatch):
    from jarvis.agents.hermes import HermesAgentEngine

    app, _, opened = assistant
    app.conversation.replace([ModelMessage(role="user", content="Explain SQL joins")])
    hermes = HermesAgentEngine(tool_service=app.tool_service)
    calls = []
    def run(engine, prompt, system_prompt):
        assert engine.tool_service is None
        calls.append(prompt)
        return json.dumps(plan("SQL joins tutorial"))
    monkeypatch.setattr(HermesAgentEngine, "run", run)
    monkeypatch.setattr(app, "_route_agent_request", lambda *args: hermes)
    assert app.interact("search for a video that I asked for").kind == "action"
    assert len(calls) == 1 and hermes.tool_service is app.tool_service
    assert query(opened[0])[0] == "www.youtube.com"


def test_constraints_survive_answering_a_missing_topic_question(assistant):
    app, model, opened = assistant
    assert app.interact("search for a video in German under 10 minutes").kind == "clarification"
    model.replies = [plan("SQL joins German tutorial under 10 minutes", source=0, source_turns=[0,1])]
    assert app.interact("SQL joins").kind == "action"
    assert query(opened[0])[1] == "SQL joins German tutorial under 10 minutes"
    data = json.loads(model.requests[0].prompt)
    assert "German under 10 minutes" in data["pending_request"]


def test_a_quoted_video_title_can_be_searched_literally(assistant):
    app, model, opened = assistant
    literal = '"I asked 100 people"'
    assert app.interact("search youtube for " + literal).kind == "action"
    assert query(opened[0])[1] == literal and not model.requests


def test_retry_of_compound_request_does_not_repeat_the_completed_video_search(assistant, monkeypatch):
    app, model, opened = assistant
    calls = []
    def sources(*args):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("Temporarily unavailable")
        return [{"title":"Observed guide", "url":"https://example.com/guide", "text":"Observed advice", "retrieved_at":"2026-11-02T12:00:00Z"}], []
    monkeypatch.setattr("jarvis.core.application.validated_sources", sources)
    model.replies = [plan("SQL joins tutorial", source=0, answer_request="Explain SQL joins"), "A join combines rows using related columns."]
    assert app.interact("Explain SQL joins and maybe show me a vd").kind == "partial"
    reply = app.interact("try again")
    assert reply.message.startswith("A join combines rows")
    assert len(opened) == 1 and len(calls) == 2


def test_a_declined_browser_shortcut_is_resolved_instead_of_reinterpreted_as_literal(assistant):
    app, model, opened = assistant
    app.interact("open github")
    model.replies = [plan("Java tutorials", source=0, engine="google")]
    reply = app.interact("search for Java tutorials in the browser you opened")
    assert reply.kind == "action" and query(opened[-1]) == ("www.google.com", "Java tutorials")
    assert len(model.requests) == 1
