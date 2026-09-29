import json

import httpx
import pytest

from jarvis.models.base import (
    ModelMessage,
    ModelRequest,
    ModelToolCall,
    ModelToolDefinition,
)
from jarvis.models.openai_compatible import (
    OpenAICompatibleProvider,
)


def _provider(
    transport: httpx.BaseTransport,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_name="test-cloud",
        model="smart-model",
        base_url="https://example.test/v1",
        api_key="secret-test-key",
        transport=transport,
    )


def test_generates_normal_chat_completion() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert (
            request.url.path
            == "/v1/chat/completions"
        )

        assert (
            request.headers[
                "Authorization"
            ]
            == "Bearer secret-test-key"
        )

        payload = json.loads(
            request.content
        )

        assert (
            payload["model"]
            == "smart-model"
        )

        assert payload[
            "messages"
        ] == [
            {
                "role": "user",
                "content": "Hello",
            }
        ]

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Hello from cloud."
                            )
                        }
                    }
                ]
            },
        )

    provider = _provider(
        httpx.MockTransport(
            handler
        )
    )

    response = provider.generate(
        ModelRequest(
            prompt="Hello"
        )
    )

    assert (
        response.text
        == "Hello from cloud."
    )

    assert (
        response.provider
        == "test-cloud"
    )

    assert (
        response.model
        == "smart-model"
    )


def test_parses_tool_call_with_id() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        del request

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-123",
                                    "type": "function",
                                    "function": {
                                        "name": (
                                            "open_application"
                                        ),
                                        "arguments": (
                                            '{"name":"Spotify"}'
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    provider = _provider(
        httpx.MockTransport(
            handler
        )
    )

    response = provider.generate(
        ModelRequest(
            prompt="Open Spotify",
            tools=[
                ModelToolDefinition(
                    name="open_application",
                    description=(
                        "Open an application."
                    ),
                    parameters={
                        "type": "object",
                    },
                )
            ],
        )
    )

    assert len(
        response.tool_calls
    ) == 1

    tool_call = response.tool_calls[
        0
    ]

    assert (
        tool_call.call_id
        == "call-123"
    )

    assert (
        tool_call.name
        == "open_application"
    )

    assert tool_call.arguments == {
        "name": "Spotify"
    }


def test_sends_tool_result_with_matching_id() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(
            request.content
        )

        messages = payload[
            "messages"
        ]

        assert messages[
            1
        ]["tool_calls"][0]["id"] == (
            "call-456"
        )

        assert messages[
            2
        ] == {
            "role": "tool",
            "tool_call_id": "call-456",
            "content": '{"ok": true}',
        }

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Done."
                        }
                    }
                ]
            },
        )

    provider = _provider(
        httpx.MockTransport(
            handler
        )
    )

    response = provider.generate(
        ModelRequest(
            prompt="Open Spotify",
            messages=[
                ModelMessage(
                    role="user",
                    content="Open Spotify",
                ),
                ModelMessage(
                    role="assistant",
                    content="",
                    tool_calls=[
                        ModelToolCall(
                            call_id="call-456",
                            name="open_application",
                            arguments={
                                "name": "Spotify"
                            },
                        )
                    ],
                ),
                ModelMessage(
                    role="tool",
                    tool_name="open_application",
                    tool_call_id="call-456",
                    content='{"ok": true}',
                ),
            ],
        )
    )

    assert response.text == "Done."


def test_invalid_tool_arguments_are_rejected() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        del request

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-bad",
                                    "type": "function",
                                    "function": {
                                        "name": "example",
                                        "arguments": (
                                            "{broken-json"
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    provider = _provider(
        httpx.MockTransport(
            handler
        )
    )

    with pytest.raises(
        ValueError,
        match="invalid JSON arguments",
    ):
        provider.generate(
            ModelRequest(
                prompt="Test"
            )
        )