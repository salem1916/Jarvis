from jarvis.models.base import (
    ModelProvider,
)
from jarvis.models.catalog import (
    ModelCatalog,
    ModelDefinition,
    ProviderDefinition,
)
from jarvis.models.discovery import (
    ModelDiscoveryService,
)
from jarvis.models.provider_registry import (
    ProviderRegistry,
)
from jarvis.runtime.profile import (
    AgentEngineId,
    ModelRole,
    ModelSelection,
    RuntimeMode,
    RuntimeProfile,
)
from jarvis.runtime.profile_store import (
    RuntimeProfileStore,
)


class ModelManager:
    """
    Central runtime model-management service.

    Both the desktop UI and CLI should eventually use this
    service instead of implementing their own provider/model
    switching logic.

    Responsibilities:

        - expose known providers
        - expose known models
        - refresh discoverable providers
        - store runtime mode
        - store agent-engine preference
        - store model-role selections
        - construct the selected ModelProvider

    It does NOT execute JARVIS tools.
    """

    def __init__(
        self,
        catalog: ModelCatalog,
        provider_registry: ProviderRegistry,
        profile: RuntimeProfile,
        profile_store: RuntimeProfileStore | None = None,
        discovery_services: tuple[
            ModelDiscoveryService,
            ...,
        ] = (),
    ) -> None:
        self.catalog = catalog

        self.provider_registry = (
            provider_registry
        )

        self._profile = profile
        self.profile_store = profile_store

        self._discovery_services = {
            service.provider_id: service
            for service
            in discovery_services
        }

    def profile(
        self,
    ) -> RuntimeProfile:
        """
        Return a copy so callers cannot silently mutate runtime
        configuration without persistence.
        """

        return self._profile.model_copy(
            deep=True
        )

    def providers(
        self,
    ) -> tuple[
        ProviderDefinition,
        ...,
    ]:
        return self.catalog.providers()

    def models(
        self,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        return self.catalog.models()

    def models_for_provider(
        self,
        provider_id: str,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        return (
            self.catalog
            .models_for_provider(
                provider_id
            )
        )

    def refresh_provider(
        self,
        provider_id: str,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        """
        Refresh one provider using its discovery service.
        """

        try:
            service = (
                self._discovery_services[
                    provider_id
                ]
            )

        except KeyError as exc:
            raise ValueError(
                "Provider does not support model discovery: "
                f"{provider_id}"
            ) from exc

        models = service.discover_models()

        self.catalog.replace_models_for_provider(
            provider_id,
            models,
        )

        return models

    def refresh_all(
        self,
    ) -> dict[
        str,
        tuple[
            ModelDefinition,
            ...,
        ],
    ]:
        """
        Refresh every provider with registered discovery.
        """

        refreshed: dict[
            str,
            tuple[
                ModelDefinition,
                ...,
            ],
        ] = {}

        for provider_id in (
            self._discovery_services
        ):
            refreshed[
                provider_id
            ] = self.refresh_provider(
                provider_id
            )

        return refreshed

    def set_mode(
        self,
        mode: RuntimeMode,
    ) -> None:
        self._profile.mode = mode
        self._persist()

    def set_agent_engine(
        self,
        agent_engine: AgentEngineId,
    ) -> None:
        self._profile.agent_engine = (
            agent_engine
        )

        self._persist()

    def set_model(
        self,
        role: ModelRole,
        provider_id: str,
        model_id: str,
    ) -> None:
        """
        Assign one known model to a runtime role.

        Unknown models are rejected rather than silently storing
        a broken configuration.
        """

        self.catalog.model(
            provider_id,
            model_id,
        )

        if not self.provider_registry.contains(
            provider_id
        ):
            raise ValueError(
                "No runtime provider is registered for: "
                f"{provider_id}"
            )

        self._profile.set_model(
            role,
            ModelSelection(
                provider_id=provider_id,
                model_id=model_id,
            ),
        )

        self._persist()

    def clear_model(
        self,
        role: ModelRole,
    ) -> None:
        self._profile.clear_model(
            role
        )

        self._persist()

    def build_provider(
        self,
        role: ModelRole,
    ) -> ModelProvider:
        """
        Construct the provider/model currently assigned to a
        runtime role.
        """

        selection = (
            self._profile.model_for(
                role
            )
        )

        if selection is None:
            raise ValueError(
                "No model is configured for runtime role: "
                f"{role.value}"
            )

        # Ensure the selection still exists.
        self.catalog.model(
            selection.provider_id,
            selection.model_id,
        )

        return self.provider_registry.create(
            selection.provider_id,
            selection.model_id,
        )

    def _persist(
        self,
    ) -> None:
        if self.profile_store is None:
            return

        self.profile_store.save(
            self._profile
        )