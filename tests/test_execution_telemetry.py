from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from jarvis.agents.base import AgentEngine
from jarvis.core.action_confirmation import (
    ActionConfirmationHandler,
)
from jarvis.core.application import JarvisApplication
from jarvis.core.conversation import Conversation
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.base import Tool
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


class StaticProvider(ModelProvider):
    name = "static"

    model = "static-model"

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        del request

        return ModelResponse(
            text="Native response.",
            provider=self.name,
            model=self.model,
        )


class RecordingContentEngine(AgentEngine):
    name = "recording-content-engine"

    def __init__(
        self,
        response: str,
    ) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.system_prompts: list[
            str
            | None
        ] = []

    def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
        conversation: Conversation | None = None,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ) = None,
    ) -> str:
        del (
            conversation,
            confirmation_handler,
        )

        self.prompts.append(
            prompt
        )

        self.system_prompts.append(
            system_prompt
        )

        return self.response


class RecordingOpenApplicationTool(Tool):
    name = "open_application"

    description = "Open application test tool."

    required_capability = Capability.OPEN_APPLICATION

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {}

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        application = arguments.get(
            "application",
            "unknown",
        )

        return {
            "ok": True,
            "action": "application_opened",
            "application": application,
        }


class RecordingOpenUrlTool(Tool):
    name = "open_url"

    description = "Open URL test tool."

    required_capability = Capability.USE_BROWSER

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {}

    def __init__(
        self,
        opened_urls: list[str],
    ) -> None:
        self.opened_urls = opened_urls

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        url = arguments.get(
            "url"
        )

        if not isinstance(
            url,
            str,
        ):
            raise TypeError(
                "'url' must be a string."
            )

        self.opened_urls.append(
            url
        )

        return {
            "ok": True,
            "action": "url_opened",
            "url": url,
        }


class RecordingCloseWindowTool(Tool):
    name = "close_window"

    description = "Close window test tool."

    required_capability = Capability.CLOSE_APPLICATION

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {}

    def __init__(
        self,
        closed_windows: list[str],
    ) -> None:
        self.closed_windows = closed_windows

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        window = arguments.get(
            "window"
        )

        if not isinstance(
            window,
            str,
        ):
            raise TypeError(
                "'window' must be a string."
            )

        self.closed_windows.append(
            window
        )

        closed_window = window

        if (
            window
            .strip()
            .casefold()
            == "facebook"
        ):
            closed_window = (
                "Facebook - Google Chrome"
            )

        return {
            "ok": True,
            "action": "close_requested",
            "window": closed_window,
        }


class RecordingKeyboardActionTool(Tool):
    name = "keyboard_action"

    description = "Keyboard action test tool."

    required_capability = Capability.KEYBOARD_ACTION

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {}

    def __init__(
        self,
        keyboard_actions: list[
            tuple[
                str,
                str,
            ]
        ],
    ) -> None:
        self.keyboard_actions = keyboard_actions

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        window = arguments.get(
            "window"
        )

        action = arguments.get(
            "action"
        )

        if not isinstance(
            window,
            str,
        ):
            raise TypeError(
                "'window' must be a string."
            )

        if not isinstance(
            action,
            str,
        ):
            raise TypeError(
                "'action' must be a string."
            )

        self.keyboard_actions.append(
            (
                window,
                action,
            )
        )

        return {
            "ok": True,
            "action": action,
            "window": (
                "Facebook - Google Chrome"
            ),
        }


class RecordingWriteFileTool(Tool):
    name = "write_file"

    description = "Write file test tool."

    required_capability = Capability.WRITE_FILE

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {}

    def __init__(
        self,
        written_files: list[
            dict[
                str,
                object,
            ]
        ],
        *,
        error: Exception | None = None,
    ) -> None:
        self.written_files = written_files
        self.error = error

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        if self.error is not None:
            raise self.error

        path = arguments.get(
            "path"
        )

        if not isinstance(
            path,
            str,
        ):
            raise TypeError(
                "'path' must be a string."
            )

        self.written_files.append(
            dict(
                arguments
            )
        )

        return {
            "ok": True,
            "action": "created",
            "path": path,
        }


def build_tool_service(
    *,
    include_open_application: bool = False,
    opened_urls: list[str] | None = None,
    closed_windows: list[str] | None = None,
    keyboard_actions: list[
        tuple[
            str,
            str,
        ]
    ] | None = None,
    written_files: list[
        dict[
            str,
            object,
        ]
    ] | None = None,
    write_error: Exception | None = None,
) -> ToolService:
    registry = ToolRegistry()

    if include_open_application:
        registry.register(
            RecordingOpenApplicationTool()
        )

    if opened_urls is not None:
        registry.register(
            RecordingOpenUrlTool(
                opened_urls
            )
        )

    if closed_windows is not None:
        registry.register(
            RecordingCloseWindowTool(
                closed_windows
            )
        )

    if keyboard_actions is not None:
        registry.register(
            RecordingKeyboardActionTool(
                keyboard_actions
            )
        )

    if written_files is not None:
        registry.register(
            RecordingWriteFileTool(
                written_files,
                error=write_error,
            )
        )

    return ToolService(
        registry,
        ToolExecutor(
            PermissionPolicy(
                allowed={
                    Capability.OPEN_APPLICATION,
                    Capability.USE_BROWSER,
                    Capability.CLOSE_APPLICATION,
                    Capability.KEYBOARD_ACTION,
                    Capability.WRITE_FILE,
                }
            )
        ),
    )


def test_fast_command_records_execution_telemetry() -> None:
    app = JarvisApplication(
        tool_service=build_tool_service(
            include_open_application=True
        ),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "Open Calculator"
    )

    assert response == "Opened Calculator."

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None

    assert telemetry.route == "FAST COMMAND"
    assert telemetry.engine == "JARVIS trusted core"
    assert telemetry.tool_name == "open_application"
    assert telemetry.duration_seconds >= 0

    assert "FAST COMMAND" in telemetry.summary()
    assert "open_application" in telemetry.summary()


def test_native_request_records_execution_telemetry() -> None:
    app = JarvisApplication(
        tool_service=build_tool_service(),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "Tell me hello"
    )

    assert response == "Native response."

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None

    assert telemetry.route == "NATIVE"
    assert telemetry.engine == "native"
    assert telemetry.model == "static-model"
    assert telemetry.tool_name is None
    assert telemetry.duration_seconds >= 0

    assert "Tell me hello" not in telemetry.summary()


def test_fast_write_file_command_uses_trusted_tool_without_ai() -> None:
    written_files: list[
        dict[
            str,
            object,
        ]
    ] = []

    app = JarvisApplication(
        tool_service=build_tool_service(
            written_files=written_files,
        ),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "okay create a file in my desktop and say hi in there"
    )

    expected_path = str(
        Path("Desktop")
        / "jarvis-note.txt"
    )

    assert written_files == [
        {
            "path": expected_path,
            "content": "hi",
            "overwrite": False,
        }
    ]

    assert response == (
        f"Wrote file: {expected_path}."
    )

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST COMMAND"
    assert telemetry.engine == "JARVIS trusted core"
    assert telemetry.tool_name == "write_file"


def test_fast_write_file_scope_error_does_not_fall_through_to_ai(
) -> None:
    written_files: list[
        dict[
            str,
            object,
        ]
    ] = []

    app = JarvisApplication(
        tool_service=build_tool_service(
            written_files=written_files,
            write_error=ValueError(
                "Path is outside the allowed filesystem scopes."
            ),
        ),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "create a file on my desktop with content hello"
    )

    expected_path = str(
        Path("Desktop")
        / "jarvis-note.txt"
    )

    assert written_files == []
    assert response == (
        "I understood the file request, but I could not write "
        f"{expected_path}: Path is outside the allowed "
        "filesystem scopes."
    )

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST COMMAND"
    assert telemetry.tool_name == "write_file"


def test_fast_write_file_creates_recipe_from_natural_desktop_request(
) -> None:
    written_files: list[
        dict[
            str,
            object,
        ]
    ] = []

    content_engine = RecordingContentEngine(
        response=(
            "Generated by Hermes:\n"
            "1. Mix the cake batter.\n"
            "2. Bake until golden."
        )
    )

    app = JarvisApplication(
        tool_service=build_tool_service(
            written_files=written_files,
        ),
        model_provider=StaticProvider(),
        hermes_agent_engine=content_engine,
    )

    response = app.ask_with_tools(

            "i need you to create a file in the desktop "
            "and put a recipe how to bake a cake"

    )

    expected_path = str(
        Path("Desktop")
        / "cake-recipe.txt"
    )

    assert len(
        written_files
    ) == 1

    assert written_files[0]["path"] == expected_path
    assert written_files[0]["overwrite"] is False

    content = written_files[0]["content"]

    assert content == (
        "Generated by Hermes:\n"
        "1. Mix the cake batter.\n"
        "2. Bake until golden."
    )

    assert content_engine.prompts == [
        (
            "Write the exact file content for this user "
            "request:\n\n"
            "a recipe how to bake a cake"
        )
    ]

    assert response == (
        f"Wrote file: {expected_path}."
    )

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST COMMAND"
    assert telemetry.tool_name == "write_file"


def test_timed_open_close_records_fast_multistep_telemetry(
    monkeypatch,
) -> None:
    opened_urls: list[str] = []
    closed_windows: list[str] = []
    keyboard_actions: list[
        tuple[
            str,
            str,
        ]
    ] = []
    slept_seconds: list[int] = []

    def fake_sleep(
        seconds: int,
    ) -> None:
        slept_seconds.append(
            seconds
        )

    monkeypatch.setattr(
        "jarvis.core.application.time.sleep",
        fake_sleep,
    )

    app = JarvisApplication(
        tool_service=build_tool_service(
            opened_urls=opened_urls,
            closed_windows=closed_windows,
            keyboard_actions=keyboard_actions,
        ),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "open facebook and wait 5 seconds and close it"
    )

    assert opened_urls == [
        "https://www.facebook.com/",
    ]

    assert slept_seconds == [
        5,
    ]

    assert closed_windows == []

    assert keyboard_actions == [
        (
            "facebook",
            "close_tab",
        )
    ]

    assert response == (
        "Opened https://www.facebook.com/. "
        "Waited 5 seconds, then requested close "
        "for Facebook - Google Chrome."
    )

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST MULTI-STEP"
    assert telemetry.engine == "JARVIS trusted core"
    assert telemetry.tool_name == (
        "open_url + wait + keyboard_action"
    )
    assert telemetry.duration_seconds >= 0


def test_memory_close_last_opened_website_uses_remembered_tab_action(
) -> None:
    opened_urls: list[str] = []
    keyboard_actions: list[
        tuple[
            str,
            str,
        ]
    ] = []

    app = JarvisApplication(
        tool_service=build_tool_service(
            opened_urls=opened_urls,
            keyboard_actions=keyboard_actions,
        ),
        model_provider=StaticProvider(),
    )

    open_response = app.ask_with_tools(
        "open facebook"
    )

    assert open_response == (
        "Opened https://www.facebook.com/."
    )
    assert opened_urls == [
        "https://www.facebook.com/",
    ]

    close_response = app.ask_with_tools(
        "close the last thing you opened"
    )

    assert close_response == (
        "Closed the last thing I opened: "
        "https://www.facebook.com/."
    )

    assert keyboard_actions == [
        (
            "facebook",
            "close_tab",
        )
    ]

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST MEMORY"
    assert telemetry.engine == "JARVIS trusted core"
    assert telemetry.tool_name == "keyboard_action"
    assert telemetry.duration_seconds >= 0


def test_memory_close_last_opened_application_uses_remembered_window_action(
) -> None:
    closed_windows: list[str] = []

    app = JarvisApplication(
        tool_service=build_tool_service(
            include_open_application=True,
            closed_windows=closed_windows,
        ),
        model_provider=StaticProvider(),
    )

    open_response = app.ask_with_tools(
        "open Calculator"
    )

    assert open_response == "Opened Calculator."

    close_response = app.ask_with_tools(
        "close what you opened"
    )

    assert close_response == (
        "Closed the last thing I opened: "
        "Calculator."
    )

    assert closed_windows == [
        "Calculator",
    ]

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST MEMORY"
    assert telemetry.tool_name == "close_window"


def test_memory_lists_open_actions() -> None:
    opened_urls: list[str] = []

    app = JarvisApplication(
        tool_service=build_tool_service(
            opened_urls=opened_urls,
        ),
        model_provider=StaticProvider(),
    )

    app.ask_with_tools(
        "open facebook"
    )

    response = app.ask_with_tools(
        "what did you open"
    )

    assert response == (
        "I remember opening: "
        "https://www.facebook.com/."
    )

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST MEMORY"
    assert telemetry.tool_name == "action_memory"


def test_memory_close_named_website_uses_remembered_action(
) -> None:
    opened_urls: list[str] = []
    keyboard_actions: list[
        tuple[
            str,
            str,
        ]
    ] = []

    app = JarvisApplication(
        tool_service=build_tool_service(
            opened_urls=opened_urls,
            keyboard_actions=keyboard_actions,
        ),
        model_provider=StaticProvider(),
    )

    app.ask_with_tools(
        "open facebook"
    )

    response = app.ask_with_tools(
        "close facebook"
    )

    assert response == (
        "Closed remembered action: "
        "https://www.facebook.com/."
    )

    assert keyboard_actions == [
        (
            "facebook",
            "close_tab",
        )
    ]

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST MEMORY"
    assert telemetry.tool_name == "keyboard_action"


def test_memory_close_unknown_target_does_not_fall_through_to_ai(
) -> None:
    app = JarvisApplication(
        tool_service=build_tool_service(),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "close facebook"
    )

    assert response == (
        "I do not have a remembered open "
        "action matching facebook."
    )

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "FAST MEMORY"
    assert telemetry.tool_name == "action_memory"


def test_assistant_pack_status_command_records_telemetry(
) -> None:
    app = JarvisApplication(
        tool_service=build_tool_service(),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "jarvis status"
    )

    assert "JARVIS status:" in response
    assert "- Main model: static-model" in response

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "ASSISTANT PACK"
    assert telemetry.engine == "JARVIS command center"
    assert telemetry.tool_name == "assistant_pack"


def test_assistant_pack_briefing_command(
) -> None:
    opened_urls: list[str] = []

    app = JarvisApplication(
        tool_service=build_tool_service(
            opened_urls=opened_urls,
        ),
        model_provider=StaticProvider(),
    )

    app.ask_with_tools(
        "open facebook"
    )

    response = app.ask_with_tools(
        "daily brief"
    )

    assert "JARVIS daily brief:" in response
    assert "https://www.facebook.com/" in response
    assert "Next big modules" in response


def test_assistant_pack_capabilities_command(
) -> None:
    app = JarvisApplication(
        tool_service=build_tool_service(),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "what can you do"
    )

    assert "JARVIS can now:" in response
    assert "Remember what it opened" in response


def test_assistant_pack_plan_command(
) -> None:
    app = JarvisApplication(
        tool_service=build_tool_service(),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "assistant plan"
    )

    assert "JARVIS product plan:" in response
    assert "Connectors" in response


def test_assistant_pack_command_center_command(
) -> None:
    app = JarvisApplication(
        tool_service=build_tool_service(),
        model_provider=StaticProvider(),
    )

    response = app.ask_with_tools(
        "command center"
    )

    assert "JARVIS command center:" in response
    assert "Hermes" in response
    assert "trusted local tools" in response

    telemetry = app.last_execution_telemetry()

    assert telemetry is not None
    assert telemetry.route == "ASSISTANT PACK"
