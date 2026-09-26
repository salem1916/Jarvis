import httpx
import pytest

from jarvis.models.base import (
    ModelRequest,
    ModelToolDefinition,
)
from jarvis.models.ollama import OllamaProvider


# Test 1:
# Verifies that a normal Ollama response is converted
# into our own ModelResponse correctly.
def test_ollama_provider_generates_response(
    monkeypatch,
):
    # We replace the real HTTP request with a fake one.
    # This means the test does NOT need a real Ollama server.
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

    # Replace httpx.post temporarily with our fake function.
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

    # Check that Ollama's response was parsed correctly.
    assert response.text == "Hello from local AI"
    assert response.provider == "ollama"
    assert response.model == "test-model"

    # A normal chat response should have no tool calls.
    assert response.tool_calls == []


# Test 2:
# Verifies that JARVIS sends the system prompt
# and user message to Ollama in the correct order.
def test_ollama_provider_sends_system_prompt(
    monkeypatch,
):
    captured_json: object | None = None

    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        nonlocal captured_json

        # Save the payload so the test can inspect it later.
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

    # This also lets Pyright know captured_json
    # is definitely a dictionary after this point.
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


# Test 3:
# Verifies that a failed connection to Ollama
# becomes a clean JARVIS RuntimeError.
def test_ollama_provider_handles_connection_error(
    monkeypatch,
):
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


# Test 4:
# Verifies two important things:
#
# 1. JARVIS sends available tool definitions to Ollama.
# 2. A tool call returned by Ollama is converted
#    into our own ModelToolCall object.
#
# IMPORTANT:
# This test does NOT execute the actual tool.
def test_ollama_provider_sends_tools_and_parses_tool_call(
    monkeypatch,
):
    captured_json: object | None = None

    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        nonlocal captured_json

        # Capture what JARVIS sends to Ollama.
        captured_json = json

        del timeout

        request = httpx.Request(
            "POST",
            url,
        )

        # Pretend that Ollama decided it wants
        # to call the list_directory tool.
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

    # Make sure JARVIS really sent a dictionary payload.
    assert isinstance(
        captured_json,
        dict,
    )

    # Make sure the Ollama request contained tool definitions.
    assert "tools" in captured_json

    # Ollama should have requested exactly one tool.
    assert len(response.tool_calls) == 1

    tool_call = response.tool_calls[0]

    # Verify that the structured tool request
    # was parsed correctly.
    assert tool_call.name == "list_directory"

    assert tool_call.arguments == {
        "path": ".",
    }