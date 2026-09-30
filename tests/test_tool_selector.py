from typing import cast

from jarvis.tools.registry import ToolRegistry
from jarvis.tools.selector import ToolSelector


class FakeTool:
    def __init__(
        self,
        name: str,
    ) -> None:
        self.name = name


class FakeRegistry:
    def __init__(
        self,
    ) -> None:
        names = (
            "list_filesystem_scopes",
            "read_file",
            "list_directory",
            "write_file",
            "trash_file",
            "list_applications",
            "open_application",
            "list_open_windows",
            "control_window",
            "close_window",
            "type_text",
            "keyboard_action",
            "list_ui_elements",
            "click_ui_element",
            "system_info",
            "calculator",
        )

        self._tools = tuple(
            FakeTool(
                name
            )
            for name in names
        )

    def tools(
        self,
    ) -> tuple[
        FakeTool,
        ...,
    ]:
        return self._tools


def _selector() -> ToolSelector:
    registry = FakeRegistry()

    return ToolSelector(
        cast(
            ToolRegistry,
            registry,
        )
    )


def _names(
    prompt: str,
) -> tuple[str, ...]:
    return tuple(
        tool.name
        for tool in _selector().select(
            prompt
        )
    )


def test_open_application_uses_small_tool_set() -> None:
    assert _names(
        "Open Spotify"
    ) == (
        "list_applications",
        "open_application",
    )


def test_open_and_click_combines_required_tools() -> None:
    assert _names(
        "Open Calculator and click 7"
    ) == (
        "list_applications",
        "open_application",
        "list_open_windows",
        "list_ui_elements",
        "click_ui_element",
    )


def test_delete_file_uses_filesystem_tools() -> None:
    assert _names(
        "Delete the file notes.txt"
    ) == (
        "list_filesystem_scopes",
        "list_directory",
        "trash_file",
    )


def test_type_text_uses_window_and_text_tools() -> None:
    assert _names(
        "Type hello into Notepad"
    ) == (
        "list_open_windows",
        "type_text",
    )


def test_unknown_request_falls_back_to_all_tools() -> None:
    tools = _names(
        "Help me think about this problem."
    )

    assert len(
        tools
    ) == 16