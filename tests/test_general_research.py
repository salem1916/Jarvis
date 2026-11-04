import json

from jarvis.agents.research import validated_sources
from jarvis.models.base import ModelProvider, ModelResponse


class ScriptedModel(ModelProvider):
    name = "test"
    def __init__(self, replies):
        self.replies = iter(replies)
    def generate(self, request):
        assert not request.tools
        return ModelResponse(text=json.dumps(next(self.replies)), provider="test", model="test")


def test_unrelated_sources_are_rejected_and_query_is_reformulated():
    model = ScriptedModel([
        {"queries": ["upcoming fixtures for Borussia Dortmund", "Borussia Dortmund schedule"]},
        {"relevant": [], "sufficient": False, "next_query": "Borussia Dortmund official upcoming fixtures"},
        {"relevant": [1], "sufficient": True},
    ])
    calls = []
    def search(query):
        calls.append(query)
        wrong = len(calls) == 1
        return {"sources": [{"title": "Retail Next" if wrong else "Club fixtures", "url": "https://next.us" if wrong else "https://club.example/fixtures", "text": "clothes" if wrong else "football fixtures"}]}
    sources, _ = validated_sources(model, search, "next matches for bvb dortmund", [])
    assert len(calls) == 2 and "official" in calls[1]
    assert [s["url"] for s in sources] == ["https://club.example/fixtures"]


def test_no_topic_specific_source_list_is_needed_for_other_topics():
    for topic in ("processor benchmarks", "train timetables", "university admission dates"):
        model = ScriptedModel([{"queries": [topic]}, {"relevant": [1], "sufficient": True}])
        sources, _ = validated_sources(model, lambda q, value=topic: {"sources": [{"url": "https://source.example", "text": value}]}, topic, [])
        assert sources and sources[0]["text"] == topic


def test_unrelated_results_do_not_become_an_answer_after_retry_budget():
    model = ScriptedModel([{"queries": ["topic"]}, {"relevant": [], "sufficient": False}, {"relevant": [], "sufficient": False}])
    calls = []
    def search(query):
        calls.append(query)
        return {"sources": [{"url": "https://unrelated.example", "text": "irrelevant"}]}
    sources, _ = validated_sources(model, search, "question", [])
    assert not sources and len(calls) == 2


def test_malformed_query_plan_falls_back_to_full_request_without_crashing():
    model = ScriptedModel([{"queries": 42}, {"relevant": [True, 0, 9, 1], "sufficient": True}])
    calls = []
    def search(query):
        calls.append(query)
        return {"sources": [{"url": "https://source.example", "text": "evidence"}]}
    sources, _ = validated_sources(model, search, "the complete original question", [])
    assert calls == ["the complete original question"] and len(sources) == 1
