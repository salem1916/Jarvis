from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field


class ModelToolDefinition(BaseModel):
    """
    Provider-independent description of a JARVIS tool.

    A model provider translates this generic definition
    into its own API-specific tool format.
    """

    name: str = Field(
        min_length=1
    )

    description: str

    parameters: dict[
        str,
        object,
    ] = Field(
        default_factory=dict
    )


class ModelToolCall(BaseModel):
    """
    Structured request from an AI model to use a tool.

    This object does NOT execute anything.

    Execution still goes through JARVIS:

        ToolService
            ↓
        PermissionPolicy
            ↓
        ToolExecutor

    call_id:

        Optional provider-generated identifier for this
        specific tool request.

        OpenAI-compatible providers use this to associate
        the later tool result with the exact assistant tool
        call that requested it.

        Providers that do not require call IDs may leave it
        as None.
    """

    call_id: str | None = None

    # Opaque provider state travels with its original call, never tool arguments.
    # Only the originating adapter interprets or sends this metadata.
    provider_metadata: dict[str, object] = Field(default_factory=dict, repr=False)

    name: str = Field(
        min_length=1
    )

    arguments: dict[
        str,
        object,
    ] = Field(
        default_factory=dict
    )


class ModelMessage(BaseModel):
    """
    One message in a model conversation.

    Roles:

    system:
        Trusted JARVIS instructions.

    user:
        The user's request.

    assistant:
        AI response and possible tool calls.

    tool:
        A REAL result returned by a JARVIS tool.
    """

    role: Literal[
        "system",
        "user",
        "assistant",
        "tool",
    ]

    content: str = ""

    # For role="tool".
    #
    # Human-readable JARVIS tool name.
    tool_name: str | None = None

    # For role="tool".
    #
    # Associates this result with the exact provider tool
    # request that produced it.
    #
    # Optional because not every provider requires IDs.
    tool_call_id: str | None = None

    # For assistant messages that request tools.
    tool_calls: list[
        ModelToolCall
    ] = Field(
        default_factory=list
    )


class ModelRequest(BaseModel):
    """
    Generic request sent to any model provider.

    prompt:
        Keeps compatibility with our original API.

    messages:
        Enables proper multi-turn conversation and
        native tool-result history.
    """

    prompt: str = Field(
        min_length=1
    )

    system_prompt: str | None = None

    # Ephemeral screenshots for a user-enabled screen session. Never put these
    # in durable chat history or tool logs. Adapters must send them as images.
    images: list[str] = Field(default_factory=list, max_length=2, repr=False)
    json_output: bool = False
    tool_choice: Literal["auto", "required"] = "auto"

    messages: list[
        ModelMessage
    ] = Field(
        default_factory=list
    )

    tools: list[
        ModelToolDefinition
    ] = Field(
        default_factory=list
    )


class ModelResponse(BaseModel):
    """
    Provider-independent model response.
    """

    text: str

    provider: str

    model: str

    tool_calls: list[
        ModelToolCall
    ] = Field(
        default_factory=list
    )


class ModelProvider(ABC):
    """
    Base interface for all JARVIS model providers.
    """

    name: str

    @abstractmethod
    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """
        Generate one model response.
        """

        raise NotImplementedError
