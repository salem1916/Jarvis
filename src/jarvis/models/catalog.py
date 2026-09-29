from enum import StrEnum

from pydantic import BaseModel, Field


class ModelLocation(StrEnum):
    """
    Where inference happens.
    """

    LOCAL = "local"
    CLOUD = "cloud"


class ProviderDefinition(BaseModel):
    """
    Metadata describing one model provider.

    This does NOT contain secrets such as API keys.
    """

    provider_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)

    location: ModelLocation

    requires_api_key: bool = False
    supports_model_discovery: bool = False
    supports_model_installation: bool = False

    openai_compatible: bool = False


class ModelDefinition(BaseModel):
    """
    Metadata describing one model available to JARVIS.

    This is intentionally separate from ModelProvider.

    ModelProvider:
        knows how to talk to a provider.

    ModelDefinition:
        tells JARVIS which model exists and what it can do.
    """

    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)

    location: ModelLocation

    supports_tools: bool = False
    supports_reasoning: bool = False
    supports_streaming: bool = False

    installable: bool = False
    installed: bool = False

    context_window: int | None = Field(
        default=None,
        gt=0,
    )

    minimum_ram_gb: float | None = Field(
        default=None,
        gt=0,
    )

    @property
    def key(self) -> str:
        """
        Stable provider/model identifier.

        Example:

            ollama:qwen3.5:4b
        """

        return (
            f"{self.provider_id}:"
            f"{self.model_id}"
        )


class ModelCatalog:
    """
    Runtime catalog of providers and models known to JARVIS.

    The catalog contains metadata only.

    It does NOT hold API keys.
    It does NOT execute inference.
    """

    def __init__(self) -> None:
        self._providers: dict[
            str,
            ProviderDefinition,
        ] = {}

        self._models: dict[
            str,
            ModelDefinition,
        ] = {}

    def register_provider(
        self,
        provider: ProviderDefinition,
    ) -> None:
        """
        Register or replace provider metadata.
        """

        self._providers[
            provider.provider_id
        ] = provider

    def register_model(
        self,
        model: ModelDefinition,
    ) -> None:
        """
        Register or replace model metadata.

        Its provider must already exist.
        """

        if (
            model.provider_id
            not in self._providers
        ):
            raise ValueError(
                "Model provider is not registered: "
                f"{model.provider_id}"
            )

        self._models[
            model.key
        ] = model

    def provider(
        self,
        provider_id: str,
    ) -> ProviderDefinition:
        """
        Return one provider.
        """

        try:
            return self._providers[
                provider_id
            ]

        except KeyError as exc:
            raise KeyError(
                "Unknown model provider: "
                f"{provider_id}"
            ) from exc

    def model(
        self,
        provider_id: str,
        model_id: str,
    ) -> ModelDefinition:
        """
        Return one specific model.
        """

        key = (
            f"{provider_id}:"
            f"{model_id}"
        )

        try:
            return self._models[
                key
            ]

        except KeyError as exc:
            raise KeyError(
                "Unknown model: "
                f"{key}"
            ) from exc

    def providers(
        self,
    ) -> tuple[
        ProviderDefinition,
        ...,
    ]:
        """
        Return all registered providers.
        """

        return tuple(
            self._providers.values()
        )

    def models(
        self,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        """
        Return all registered models.
        """

        return tuple(
            self._models.values()
        )

    def models_for_provider(
        self,
        provider_id: str,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        """
        Return models belonging to one provider.
        """

        return tuple(
            model
            for model
            in self._models.values()
            if (
                model.provider_id
                == provider_id
            )
        )