import httpx

from jarvis.models.catalog import (
    ModelDefinition,
    ModelLocation,
)


class OllamaDiscoveryService:
    """
    Discover models installed in the user's local Ollama
    installation.

    Discovery uses Ollama's local HTTP API:

        GET /api/tags

    Discovery does NOT install or delete anything.

    It is therefore safe to use for refreshing the future
    Models page.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip(
            "/"
        )

        self.timeout = timeout
        self.transport = transport

    def discover_models(
        self,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        """
        Return the models currently installed in Ollama.

        The /api/tags endpoint identifies installed models but
        does not give JARVIS enough provider-independent
        capability information to safely infer every feature.

        Capability probing will therefore be a separate layer.
        """

        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.get(
                    f"{self.base_url}/api/tags"
                )

                response.raise_for_status()

                data = response.json()

        except (
            httpx.HTTPError,
            ValueError,
        ) as exc:
            raise RuntimeError(
                "Could not discover local Ollama models."
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "Ollama model discovery returned "
                "an invalid response."
            )

        raw_models = data.get(
            "models"
        )

        if not isinstance(
            raw_models,
            list,
        ):
            raise TypeError(
                "Ollama model discovery returned "
                "an invalid models list."
            )

        discovered: dict[
            str,
            ModelDefinition,
        ] = {}

        for raw_model in raw_models:
            if not isinstance(
                raw_model,
                dict,
            ):
                raise TypeError(
                    "Ollama returned an invalid model entry."
                )

            raw_model_id = raw_model.get(
                "model"
            )

            if not isinstance(
                raw_model_id,
                str,
            ):
                raw_model_id = raw_model.get(
                    "name"
                )

            if (
                not isinstance(
                    raw_model_id,
                    str,
                )
                or not raw_model_id.strip()
            ):
                raise TypeError(
                    "Ollama model entry has no valid name."
                )

            model_id = raw_model_id.strip()

            discovered[
                model_id
            ] = ModelDefinition(
                provider_id="ollama",
                model_id=model_id,
                display_name=model_id,
                location=ModelLocation.LOCAL,

                # It is already present locally.
                installed=True,

                # Later the model manager will support
                # ollama pull / delete through trusted code.
                installable=True,

                # Ollama's chat API supports streaming.
                supports_streaming=True,

                # We intentionally do NOT guess these from
                # the model's name.
                #
                # A capability-probing service will determine
                # these accurately later.
                supports_tools=False,
                supports_reasoning=False,
            )

        return tuple(
            discovered.values()
        )
    