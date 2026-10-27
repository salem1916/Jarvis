from __future__ import annotations

import httpx

from jarvis.models.catalog import (
    ModelDefinition,
    ModelLocation,
)
from jarvis.models.discovery import ModelDiscoveryService


class OpenAICompatibleDiscoveryService(
    ModelDiscoveryService
):
    """
    Discover models from any provider exposing an
    OpenAI-compatible GET /models endpoint.

    This works for providers such as:

        OpenRouter
        Groq
        Gemini OpenAI compatibility
        DeepSeek
        xAI
        LM Studio
        many future local/cloud servers

    Discovery performs no inference.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        location: ModelLocation,
        api_key: str | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        provider_id = provider_id.strip()

        if not provider_id:
            raise ValueError(
                "provider_id cannot be empty."
            )

        base_url = base_url.strip().rstrip(
            "/"
        )

        if not base_url:
            raise ValueError(
                "base_url cannot be empty."
            )

        if timeout <= 0:
            raise ValueError(
                "timeout must be greater than zero."
            )

        self.provider_id = provider_id
        self.base_url = base_url
        self.location = location

        self.api_key = (
            api_key.strip()
            if api_key
            else None
        )

        self.timeout = timeout
        self.transport = transport

    def discover_models(
        self,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        headers: dict[
            str,
            str,
        ] = {}

        if self.api_key:
            headers[
                "Authorization"
            ] = (
                f"Bearer {self.api_key}"
            )

        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.get(
                    f"{self.base_url}/models",
                    headers=headers,
                )

                response.raise_for_status()

                payload = response.json()

        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Could not discover models from "
                f"{self.provider_id}."
            ) from exc

        except ValueError as exc:
            raise RuntimeError(
                f"{self.provider_id} returned invalid JSON."
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise TypeError(
                "Model discovery returned an invalid response."
            )

        raw_models = payload.get(
            "data"
        )

        if not isinstance(
            raw_models,
            list,
        ):
            raise TypeError(
                "Model discovery response has no model list."
            )

        discovered: list[
            ModelDefinition
        ] = []

        seen: set[
            str
        ] = set()

        for raw_model in raw_models:
            if not isinstance(
                raw_model,
                dict,
            ):
                continue

            model_id = raw_model.get(
                "id"
            )

            if (
                not isinstance(
                    model_id,
                    str,
                )
                or not model_id.strip()
            ):
                continue

            model_id = model_id.strip()

            if model_id in seen:
                continue

            seen.add(
                model_id
            )

            discovered.append(
                ModelDefinition(
                    provider_id=(
                        self.provider_id
                    ),
                    model_id=model_id,
                    display_name=model_id,
                    location=self.location,
                    supports_tools=False,
                    supports_reasoning=False,
                    supports_streaming=True,
                    installable=False,
                    installed=(
                        self.location
                        is ModelLocation.LOCAL
                    ),
                )
            )

        discovered.sort(
            key=lambda model: (
                model.model_id.lower()
            )
        )

        return tuple(
            discovered
        )