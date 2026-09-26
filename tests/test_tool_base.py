from collections.abc import Mapping

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class DummyReadTool(Tool):
    name = "dummy_read"
    description = "A test tool."
    required_capability = Capability.READ_FILE

    def execute(self, arguments: Mapping[str, object]) -> object:
        return "ok"


def test_tool_has_required_metadata():
    tool = DummyReadTool()

    assert tool.name == "dummy_read"
    assert tool.description == "A test tool."
    assert tool.required_capability == Capability.READ_FILE


def test_tool_can_execute():
    tool = DummyReadTool()

    assert tool.execute({}) == "ok"