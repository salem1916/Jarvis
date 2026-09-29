from collections.abc import Callable

from jarvis.models.base import ModelProvider

ModelProviderFactory = Callable[
    [str],
    ModelProvider,
]


class ProviderRegistry:
    """
    Registry of model-provider factories.

    Provider metadata belongs in ModelCatalog.

    This registry answers a different question:

        "How do I actually create a provider instance
         for this provider/model combination?"

    Example:

        registry.create(
            "ollama",
            "qwen3.5:4b",
        )

    may produce:

        OllamaProvider(
            model="qwen3.5:4b"
        )
    """

    def __init__(
        self,
    ) -> None:
        self._factories: dict[
            str,
            ModelProviderFactory,
        ] = {}

    def register(
        self,
        provider_id: str,
        factory: ModelProviderFactory,
    ) -> None:
        """
        Register one provider factory.

        Duplicate registration is treated as an error so a
        bootstrap mistake cannot silently replace a provider.
        """

        normalized = provider_id.strip()

        if not normalized:
            raise ValueError(
                "provider_id cannot be empty."
            )

        if normalized in self._factories:
            raise ValueError(
                "Model provider is already registered: "
                f"{normalized}"
            )

        self._factories[
            normalized
        ] = factory

    def create(
        self,
        provider_id: str,
        model_id: str,
    ) -> ModelProvider:
        """
        Create a provider configured for one model.
        """

        try:
            factory = self._factories[
                provider_id
            ]

        except KeyError as exc:
            raise KeyError(
                "Unknown model provider: "
                f"{provider_id}"
            ) from exc

        return factory(
            model_id
        )

    def contains(
        self,
        provider_id: str,
    ) -> bool:
        """
        Return whether the provider is registered.
        """

        return (
            provider_id
            in self._factories
        )

    def provider_ids(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        """
        Return all registered provider IDs.
        """

        return tuple(
            self._factories
        )