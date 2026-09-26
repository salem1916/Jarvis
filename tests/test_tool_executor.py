from collections.abc import Mapping

import pytest

from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.base import Tool
from jarvis.tools.executor import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    ToolExecutor,
)


class DummyReadTool(Tool):
    name = "dummy_read"
    description = "A dummy read tool."
    required_capability = Capability.READ_FILE

    def execute(self, arguments: Mapping[str, object]) -> object:
        return "executed"


def test_allowed_tool_executes():
    policy = PermissionPolicy(
        allowed={Capability.READ_FILE},
    )
    executor = ToolExecutor(policy)
    tool = DummyReadTool()

    result = executor.execute(tool, {})

    assert result == "executed"


def test_denied_tool_does_not_execute():
    policy = PermissionPolicy()
    executor = ToolExecutor(policy)
    tool = DummyReadTool()

    with pytest.raises(PermissionDeniedError):
        executor.execute(tool, {})


def test_confirmation_required_blocks_execution():
    policy = PermissionPolicy(
        require_confirmation={Capability.READ_FILE},
    )
    executor = ToolExecutor(policy)
    tool = DummyReadTool()

    with pytest.raises(ConfirmationRequiredError):
        executor.execute(tool, {})