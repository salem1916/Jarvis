import httpx
import pytest

from jarvis.models.base import ModelRequest
from jarvis.models.ollama import OllamaProvider


def test_ollama_provider_generates_response(monkeypatch):
    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        del json, timeout

        request = httpx.Request("POST", url)

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

    monkeypatch.setattr(httpx, "post", fake_post)

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


def test_ollama_provider_sends_system_prompt(monkeypatch):
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

        request = httpx.Request("POST", url)

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

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OllamaProvider(
        model="test-model",
    )

    provider.generate(
        ModelRequest(
            prompt="Hello",
            system_prompt="You are JARVIS.",
        )
    )

    assert isinstance(captured_json, dict)

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


def test_ollama_provider_handles_connection_error(monkeypatch):
    def fake_post(
        url: str,
        *,
        json: object,
        timeout: float,
    ) -> httpx.Response:
        del url, json, timeout

        raise httpx.ConnectError("Connection failed")

    monkeypatch.setattr(httpx, "post", fake_post)

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