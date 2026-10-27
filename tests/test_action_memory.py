from pathlib import Path

from jarvis.core.action_memory import ActionMemory
from jarvis.core.tool_request import ToolRequest


def test_action_memory_persists_entries(
    tmp_path: Path,
) -> None:
    store_path = (
        tmp_path
        / "action_memory.json"
    )

    memory = ActionMemory.load(
        store_path
    )

    entry = memory.remember_opened(
        label="https://www.facebook.com/",
        open_request=ToolRequest(
            tool_name="open_url",
            arguments={
                "url": "https://www.facebook.com/",
            },
        ),
        close_request=ToolRequest(
            tool_name="keyboard_action",
            arguments={
                "window": "facebook",
                "action": "close_tab",
            },
        ),
        opened_at=10.0,
    )

    memory.mark_closed(
        entry.entry_id,
        closed_at=12.0,
    )

    loaded = ActionMemory.load(
        store_path
    )

    entries = loaded.entries()

    assert len(
        entries
    ) == 1

    loaded_entry = entries[0]

    assert loaded_entry.label == (
        "https://www.facebook.com/"
    )

    assert loaded_entry.open_request.tool_name == "open_url"
    assert loaded_entry.close_request.tool_name == "keyboard_action"
    assert loaded_entry.closed_at == 12.0


def test_action_memory_finds_open_entry_by_domain(
    tmp_path: Path,
) -> None:
    del tmp_path

    memory = ActionMemory()

    memory.remember_opened(
        label="https://www.facebook.com/",
        open_request=ToolRequest(
            tool_name="open_url",
            arguments={
                "url": "https://www.facebook.com/",
            },
        ),
        close_request=ToolRequest(
            tool_name="keyboard_action",
            arguments={
                "window": "facebook",
                "action": "close_tab",
            },
        ),
        opened_at=10.0,
    )

    entry = memory.find_open_entry(
        "facebook"
    )

    assert entry is not None
    assert entry.label == "https://www.facebook.com/"
