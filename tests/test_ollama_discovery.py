import httpx
import pytest

from jarvis.models.ollama_discovery import (
    OllamaDiscoveryService,
)


def test_discovers_installed_ollama_models() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert (
            request.url.path
            == "/api/tags"
        )

        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen3.5:4b",
                        "model": "qwen3.5:4b",
                    },
                    {
                        "name": "example:latest",
                        "model": "example:latest",
                    },
                ]
            },
        )

    service = OllamaDiscoveryService(
        transport=httpx.MockTransport(
            handler
        )
    )

    models = service.discover_models()

    assert [
        model.model_id
        for model in models
    ] == [
        "qwen3.5:4b",
        "example:latest",
    ]

    assert all(
        model.installed
        for model in models
    )

    assert all(
        model.provider_id
        == "ollama"
        for model in models
    )


def test_empty_ollama_installation_is_valid() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        del request

        return httpx.Response(
            200,
            json={
                "models": []
            },
        )

    service = OllamaDiscoveryService(
        transport=httpx.MockTransport(
            handler
        )
    )

    assert (
        service.discover_models()
        == ()
    )


def test_invalid_ollama_response_is_rejected() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        del request

        return httpx.Response(
            200,
            json={
                "models": "invalid"
            },
        )

    service = OllamaDiscoveryService(
        transport=httpx.MockTransport(
            handler
        )
    )

    with pytest.raises(
        TypeError,
        match="invalid models list",
    ):
        service.discover_models()


def test_ollama_http_failure_is_wrapped() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        del request

        return httpx.Response(
            503
        )

    service = OllamaDiscoveryService(
        transport=httpx.MockTransport(
            handler
        )
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Could not discover "
            "local Ollama models"
        ),
    ):
        service.discover_models()