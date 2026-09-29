from dataclasses import dataclass
from typing import cast

import pytest

from jarvis.core.agent_service import (
    AgentIncompleteTaskError,
    AgentService,
)
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelToolCall,
)
from jarvis.security.capabilities import Capability
from jarvis.tools.service import ToolService


@dataclass(
    frozen=True,
)
class FakeResponse:
    """
    Scripted model response used by the reliability tests.

    Tool calls deliberately use the REAL ModelToolCall type.

    This matters because AgentService stores model responses
    inside ModelMessage, whose Pydantic schema validates
    tool_calls as ModelToolCall instances.
    """

    text: str

    tool_calls: tuple[
        ModelToolCall,
        ...,
    ]


@dataclass(
    frozen=True,
)
class FakeTool:
    """
    Minimal fake tool definition used by the test registry.
    """

    name: str
    required_capability: Capability

    description: str = "Fake test tool"

    parameters_schema: dict[
        str,
        object,
    ] | None = None

    def __post_init__(
        self,
    ) -> None:
        if self.parameters_schema is None:
            object.__setattr__(
                self,
                "parameters_schema",
                {
                    "type": "object",
                    "properties": {},
                },
            )


class FakeRegistry:
    """
    Small fake ToolRegistry implementation.

    It provides only the methods AgentService needs in these
    tests.
    """

    def __init__(
        self,
        tools: tuple[
            FakeTool,
            ...,
        ],
    ) -> None:
        self._tools = tools

    def tools(
        self,
    ) -> tuple[
        FakeTool,
        ...,
    ]:
        return self._tools

    def get(
        self,
        name: str,
    ) -> FakeTool:
        for tool in self._tools:
            if tool.name == name:
                return tool

        raise KeyError(
            name
        )


class FakeToolService:
    """
    Fake ToolService used to verify which actions the agent
    actually executes.

    Observation:
        list_ui_elements

    Side effect:
        click_ui_element
    """

    def __init__(
        self,
        registry: FakeRegistry,
    ) -> None:
        self.registry = registry

        self.executed: list[
            str
        ] = []

    def execute(
        self,
        request: ToolRequest,
        confirmed: bool = False,
    ) -> object:
        del confirmed

        self.executed.append(
            request.tool_name
        )

        if (
            request.tool_name
            == "list_ui_elements"
        ):
            return [
                {
                    "name": "7",
                    "control_type": "Button",
                    "enabled": True,
                }
            ]

        if (
            request.tool_name
            == "click_ui_element"
        ):
            return {
                "ok": True,
                "action": "ui_element_clicked",
                "window": "Calculator",
                "element": "7",
                "control_type": "Button",
            }

        raise ValueError(
            "Unexpected fake tool."
        )


class ScriptedModelProvider:
    """
    Deterministic fake model.

    Every call returns the next preconfigured response.

    This lets us test the agent loop without relying on Ollama.
    """

    def __init__(
        self,
        responses: list[
            FakeResponse
        ],
    ) -> None:
        self.responses = responses

        self.requests: list[
            object
        ] = []

    def generate(
        self,
        request: object,
    ) -> FakeResponse:
        self.requests.append(
            request
        )

        if not self.responses:
            raise AssertionError(
                "Fake model ran out of scripted responses."
            )

        return self.responses.pop(
            0
        )


def _build_service(
    responses: list[
        FakeResponse
    ],
    *,
    max_completion_retries: int = 2,
) -> tuple[
    AgentService,
    FakeToolService,
    ScriptedModelProvider,
]:
    """
    Build an AgentService using deterministic fake model and
    tool layers.
    """

    registry = FakeRegistry(
        (
            FakeTool(
                name="list_ui_elements",
                required_capability=(
                    Capability.INSPECT_UI
                ),
            ),
            FakeTool(
                name="click_ui_element",
                required_capability=(
                    Capability.CLICK_UI
                ),
            ),
        )
    )

    tool_service = FakeToolService(
        registry
    )

    provider = ScriptedModelProvider(
        responses
    )

    service = AgentService(
        model_provider=cast(
            ModelProvider,
            provider,
        ),
        tool_service=cast(
            ToolService,
            tool_service,
        ),
        max_tool_rounds=5,
        max_completion_retries=(
            max_completion_retries
        ),
    )

    return (
        service,
        tool_service,
        provider,
    )


def test_action_request_does_not_stop_after_observation() -> None:
    """
    Regression test for the Calculator problem.

    User:
        Click 7.

    Bad model behavior:

        inspect controls
            ↓
        stop early

    Required JARVIS behavior:

        inspect controls
            ↓
        CLICK_UI still missing
            ↓
        force another model turn
            ↓
        click_ui_element succeeds
            ↓
        final answer allowed
    """

    service, tool_service, provider = _build_service(
        [
            # -------------------------------------------------
            # Turn 1:
            # The model observes Calculator.
            # -------------------------------------------------

            FakeResponse(
                text="",
                tool_calls=(
                    ModelToolCall(
                        name="list_ui_elements",
                        arguments={
                            "window": "Calculator",
                        },
                    ),
                ),
            ),

            # -------------------------------------------------
            # Turn 2:
            #
            # The weak model incorrectly tries to stop after
            # merely observing the controls.
            #
            # AgentService must reject this final answer because
            # CLICK_UI has not succeeded.
            # -------------------------------------------------

            FakeResponse(
                text=(
                    "I found the Calculator controls."
                ),
                tool_calls=(),
            ),

            # -------------------------------------------------
            # Turn 3:
            #
            # Execution guard sends the model back to work.
            # It now performs the actual side effect.
            # -------------------------------------------------

            FakeResponse(
                text="",
                tool_calls=(
                    ModelToolCall(
                        name="click_ui_element",
                        arguments={
                            "window": "Calculator",
                            "element": "7",
                            "control_type": "Button",
                        },
                    ),
                ),
            ),

            # -------------------------------------------------
            # Turn 4:
            #
            # CLICK_UI has succeeded, so the final response is
            # now grounded in trusted execution evidence.
            # -------------------------------------------------

            FakeResponse(
                text="Done.",
                tool_calls=(),
            ),
        ]
    )

    result = service.run(
        "Click the 7 button in Calculator."
    )

    assert result == "Done."

    assert tool_service.executed == [
        "list_ui_elements",
        "click_ui_element",
    ]

    assert len(
        provider.requests
    ) == 4


def test_informational_ui_request_can_finish_after_inspection() -> None:
    """
    Read-only questions must not be forced into side effects.

    Asking:

        What controls can you see?

    is different from:

        Click 7.
    """

    service, tool_service, _provider = _build_service(
        [
            FakeResponse(
                text="",
                tool_calls=(
                    ModelToolCall(
                        name="list_ui_elements",
                        arguments={
                            "window": "Calculator",
                        },
                    ),
                ),
            ),
            FakeResponse(
                text=(
                    "Calculator contains a button named 7."
                ),
                tool_calls=(),
            ),
        ]
    )

    result = service.run(
        "What UI controls can you see in Calculator?"
    )

    assert result == (
        "Calculator contains a button named 7."
    )

    assert tool_service.executed == [
        "list_ui_elements",
    ]


def test_agent_refuses_fake_success_after_retry_limit() -> None:
    """
    If the model repeatedly claims it performed an action
    without using the required tool, JARVIS must fail instead
    of accepting the hallucination.
    """

    service, tool_service, _provider = _build_service(
        [
            FakeResponse(
                text="I clicked 7.",
                tool_calls=(),
            ),
            FakeResponse(
                text="Done.",
                tool_calls=(),
            ),
        ],
        max_completion_retries=1,
    )

    with pytest.raises(
        AgentIncompleteTaskError,
        match="CLICK_UI",
    ):
        service.run(
            "Click the 7 button in Calculator."
        )

    assert tool_service.executed == []


def test_multi_step_request_requires_multiple_capabilities() -> None:
    """
    A simple multi-step user command should create multiple
    trusted completion requirements.
    """

    required = (
        AgentService
        ._infer_required_capabilities(
            
                "Open Notepad, type hello, "
                "then save it."
            
        )
    )

    assert (
        Capability.OPEN_APPLICATION
        in required
    )

    assert (
        Capability.TYPE_TEXT
        in required
    )

    assert (
        Capability.KEYBOARD_ACTION
        in required
    )


def test_question_about_action_does_not_require_execution() -> None:
    """
    Asking HOW to perform an action must not accidentally
    cause JARVIS to perform that action.
    """

    required = (
        AgentService
        ._infer_required_capabilities(
            "How do I open Calculator?"
        )
    )

    assert required == frozenset()