import pytest
from pydantic import ValidationError

from jarvis.core.tool_request import ToolRequest


def test_tool_request_stores_name_and_arguments():
    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": "notes.txt"},
    )

    assert request.tool_name == "read_file"
    assert request.arguments == {"path": "notes.txt"}


def test_tool_request_defaults_to_empty_arguments():
    request = ToolRequest(tool_name="read_file")

    assert request.arguments == {}


def test_tool_request_rejects_empty_tool_name():
    with pytest.raises(ValidationError):
        ToolRequest(tool_name="")