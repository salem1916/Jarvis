from typing import Protocol

from jarvis.models.catalog import ModelDefinition


class ModelDiscoveryService(Protocol):
    """
    Provider-independent model discovery interface.

    Examples:

        OllamaDiscoveryService
        future cloud-provider discovery services

    Discovery finds models.

    It does not execute inference and does not change the
    user's active runtime configuration.
    """

    provider_id: str

    def discover_models(
        self,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        """
        Return models currently available from this provider.
        """

        ...