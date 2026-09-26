import httpx
import pytest

from jarvis.models.base import (
    ModelMessage,
    ModelRequest,
    ModelToolCall,
    ModelToolDefinition,
)
from jarvis.models.ollama import OllamaProvider

# ---------------------------------------------------------
# TEST 1
# Normal text response
# ---------------------------------------------------------


def test_ollama_provider_generates_response(
    monkeypatch,
) -> None:
    """
    Verify that a normal Ollama text response is
    converted into JARVIS's ModelResponse correctly.
    """

    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        del json, timeout

        request = httpx.Request(
            "POST",
            url,
        )

        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "message": {
                    "role": "assistant",
                    "content": "Hello from local AI",
                }
            },
        )

    # Replace the real HTTP request with our fake one.
    monkeypatch.setattr(
        httpx,
        "post",
        fake_post,
    )

    provider = OllamaProvider(
        model="test-model",
    )

    response = provider.generate(
        ModelRequest(
            prompt="Hello",
        )
    )

    assert response.text == "Hello from local AI"
    assert response.provider == "ollama"
    assert response.model == "test-model"

    # Normal chat should not contain tool calls.
    assert response.tool_calls == []


# ---------------------------------------------------------
# TEST 2
# System prompt
# ---------------------------------------------------------


def test_ollama_provider_sends_system_prompt(
    monkeypatch,
) -> None:
    """
    Verify that the system prompt is sent before
    the user's message.
    """

    captured_json: object | None = None

    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        nonlocal captured_json

        captured_json = json

        del timeout

        request = httpx.Request(
            "POST",
            url,
        )

        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "message": {
                    "role": "assistant",
                    "content": "ok",
                }
            },
        )

    monkeypatch.setattr(
        httpx,
        "post",
        fake_post,
    )

    provider = OllamaProvider(
        model="test-model",
    )

    provider.generate(
        ModelRequest(
            prompt="Hello",
            system_prompt="You are JARVIS.",
        )
    )

    assert isinstance(
        captured_json,
        dict,
    )

    assert captured_json["messages"] == [
        {
            "role": "system",
            "content": "You are JARVIS.",
        },
        {
            "role": "user",
            "content": "Hello",
        },
    ]


# ---------------------------------------------------------
# TEST 3
# Connection failure
# ---------------------------------------------------------


def test_ollama_provider_handles_connection_error(
    monkeypatch,
) -> None:
    """
    Verify that an Ollama connection failure becomes
    a clean RuntimeError inside JARVIS.
    """

    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        del url, json, timeout

        raise httpx.ConnectError(
            "Connection failed"
        )

    monkeypatch.setattr(
        httpx,
        "post",
        fake_post,
    )

    provider = OllamaProvider(
        model="test-model",
    )

    with pytest.raises(
        RuntimeError,
        match="Could not communicate with the Ollama server",
    ):
        provider.generate(
            ModelRequest(
                prompt="Hello",
            )
        )


# ---------------------------------------------------------
# TEST 4
# Tool definitions + tool-call parsing
# ---------------------------------------------------------


def test_ollama_provider_sends_tools_and_parses_tool_call(
    monkeypatch,
) -> None:
    """
    Verify two things:

    1. JARVIS sends available tools to Ollama.
    2. Ollama's tool-call response is converted into
       JARVIS's generic ModelToolCall format.

    IMPORTANT:
    No real tool is executed here.
    """

    captured_json: object | None = None

    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        nonlocal captured_json

        captured_json = json

        del timeout

        request = httpx.Request(
            "POST",
            url,
        )

        # Pretend Ollama decided that it needs
        # list_directory.
        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "list_directory",
                                "arguments": {
                                    "path": ".",
                                },
                            },
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(
        httpx,
        "post",
        fake_post,
    )

    provider = OllamaProvider(
        model="test-model",
    )

    response = provider.generate(
        ModelRequest(
            prompt="What files are in my workspace?",
            tools=[
                ModelToolDefinition(
                    name="list_directory",
                    description=(
                        "List files and folders "
                        "inside the workspace."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                            }
                        },
                        "additionalProperties": False,
                    },
                )
            ],
        )
    )

    assert isinstance(
        captured_json,
        dict,
    )

    # Ensure tool definitions were really sent to Ollama.
    assert "tools" in captured_json

    # Ollama should have requested exactly one tool.
    assert len(response.tool_calls) == 1

    tool_call = response.tool_calls[0]

    assert tool_call.name == "list_directory"

    assert tool_call.arguments == {
        "path": ".",
    }


# ---------------------------------------------------------
# TEST 5
# Native multi-turn tool history
# ---------------------------------------------------------


def test_ollama_provider_sends_native_tool_history(
    monkeypatch,
) -> None:
    """
    Verify that JARVIS sends Ollama a REAL multi-turn
    tool conversation.

    The expected flow is:

        user
          ↓
        assistant requests tool
          ↓
        role="tool" contains the REAL result
          ↓
        model continues

    This is better than rewriting tool results into
    another fake user prompt.
    """

    captured_json: object | None = None

    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        nonlocal captured_json

        captured_json = json

        del timeout

        request = httpx.Request(
            "POST",
            url,
        )

        # Pretend Ollama has now received the real tool
        # result and produces the final answer.
        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "message": {
                    "role": "assistant",
                    "content": (
                        "The workspace contains hello.txt."
                    ),
                }
            },
        )

    monkeypatch.setattr(
        httpx,
        "post",
        fake_post,
    )

    provider = OllamaProvider(
        model="test-model",
    )

    provider.generate(
        ModelRequest(
            prompt="What files are in my workspace?",
            messages=[
                # User asks a normal question.
                ModelMessage(
                    role="user",
                    content=(
                        "What files are in my workspace?"
                    ),
                ),

                # Assistant decides to use list_directory.
                ModelMessage(
                    role="assistant",
                    tool_calls=[
                        ModelToolCall(
                            name="list_directory",
                            arguments={
                                "path": ".",
                            },
                        )
                    ],
                ),

                # JARVIS returns the REAL tool result.
                ModelMessage(
                    role="tool",
                    tool_name="list_directory",
                    content='["hello.txt"]',
                ),
            ],
            tools=[
                ModelToolDefinition(
                    name="list_directory",
                    description=(
                        "List workspace files."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                            }
                        },
                    },
                )
            ],
        )
    )

    assert isinstance(
        captured_json,
        dict,
    )

    messages = captured_json[
        "messages"
    ]

    assert isinstance(
        messages,
        list,
    )

    # This is the important assertion.
    #
    # We want Ollama to receive the real native sequence:
    #
    # user
    # assistant + tool_calls
    # tool result
    assert messages == [
        {
            "role": "user",
            "content": (
                "What files are in my workspace?"
            ),
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "list_directory",
                        "arguments": {
                            "path": ".",
                        },
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": '["hello.txt"]',
            "tool_name": "list_directory",
        },
    ]