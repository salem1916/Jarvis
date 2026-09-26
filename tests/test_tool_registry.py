from collections.abc import Mapping

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.registry import ToolRegistry


class DummyTool(Tool):
    name = "dummy"
    description = "A dummy tool."
    required_capability = Capability.READ_FILE

    def execute(self, arguments: Mapping[str, object]) -> object:
        return "ok"


def test_registry_registers_and_returns_tool():
    registry = ToolRegistry()
    tool = DummyTool()

    registry.register(tool)

    assert registry.get("dummy") is tool


def test_registry_lists_registered_tool_names():
    registry = ToolRegistry()
    registry.register(DummyTool())

    assert registry.names() == ("dummy",)


def test_registry_rejects_duplicate_tool_names():
    registry = ToolRegistry()
    registry.register(DummyTool())

    with pytest.raises(ValueError):
        registry.register(DummyTool())


def test_registry_rejects_unknown_tool():
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        registry.get("missing")