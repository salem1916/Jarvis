from pathlib import Path

import pytest

from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from jarvis.models.catalog import (
    ModelCatalog,
    ModelDefinition,
    ModelLocation,
    ProviderDefinition,
)
from jarvis.models.provider_registry import (
    ProviderRegistry,
)
from jarvis.runtime.model_manager import (
    ModelManager,
)
from jarvis.runtime.profile import (
    AgentEngineId,
    ModelRole,
    RuntimeMode,
    RuntimeProfile,
)
from jarvis.runtime.profile_store import (
    RuntimeProfileStore,
)


class FakeProvider(
    ModelProvider
):
    name = "fake"

    def __init__(
        self,
        model: str,
    ) -> None:
        self.model = model

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        del request

        return ModelResponse(
            text="fake",
            provider=self.name,
            model=self.model,
        )


class FakeDiscovery:
    provider_id = "fake"

    def __init__(
        self,
        models: tuple[
            ModelDefinition,
            ...,
        ],
    ) -> None:
        self.models = models

    def discover_models(
        self,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        return self.models


def _build_manager(
    tmp_path: Path,
) -> ModelManager:
    catalog = ModelCatalog()

    catalog.register_provider(
        ProviderDefinition(
            provider_id="fake",
            display_name="Fake",
            location=ModelLocation.LOCAL,
            supports_model_discovery=True,
        )
    )

    registry = ProviderRegistry()

    registry.register(
        "fake",
        lambda model_id: FakeProvider(
            model_id
        ),
    )

    discovery = FakeDiscovery(
        (
            ModelDefinition(
                provider_id="fake",
                model_id="model-a",
                display_name="Model A",
                location=ModelLocation.LOCAL,
                installed=True,
            ),
            ModelDefinition(
                provider_id="fake",
                model_id="model-b",
                display_name="Model B",
                location=ModelLocation.LOCAL,
                installed=True,
            ),
        )
    )

    store = RuntimeProfileStore(
        tmp_path
        / "runtime_profile.json"
    )

    return ModelManager(
        catalog=catalog,
        provider_registry=registry,
        profile=RuntimeProfile(),
        profile_store=store,
        discovery_services=(
            discovery,
        ),
    )


def test_refresh_discovers_models(
    tmp_path: Path,
) -> None:
    manager = _build_manager(
        tmp_path
    )

    models = manager.refresh_provider(
        "fake"
    )

    assert [
        model.model_id
        for model in models
    ] == [
        "model-a",
        "model-b",
    ]

    assert len(
        manager.models()
    ) == 2


def test_runtime_choices_are_persisted(
    tmp_path: Path,
) -> None:
    manager = _build_manager(
        tmp_path
    )

    manager.refresh_provider(
        "fake"
    )

    manager.set_mode(
        RuntimeMode.SMART
    )

    manager.set_agent_engine(
        AgentEngineId.HERMES
    )

    manager.set_model(
        ModelRole.MAIN,
        "fake",
        "model-a",
    )

    loaded = RuntimeProfileStore(
        tmp_path
        / "runtime_profile.json"
    ).load()

    assert (
        loaded.mode
        == RuntimeMode.SMART
    )

    assert (
        loaded.agent_engine
        == AgentEngineId.HERMES
    )

    selection = loaded.model_for(
        ModelRole.MAIN
    )

    assert selection is not None

    assert (
        selection.model_id
        == "model-a"
    )


def test_build_provider_uses_selected_model(
    tmp_path: Path,
) -> None:
    manager = _build_manager(
        tmp_path
    )

    manager.refresh_provider(
        "fake"
    )

    manager.set_model(
        ModelRole.MAIN,
        "fake",
        "model-b",
    )

    provider = manager.build_provider(
        ModelRole.MAIN
    )

    assert isinstance(
        provider,
        FakeProvider,
    )

    assert (
        provider.model
        == "model-b"
    )


def test_unknown_model_cannot_be_selected(
    tmp_path: Path,
) -> None:
    manager = _build_manager(
        tmp_path
    )

    with pytest.raises(
        KeyError,
        match="Unknown model",
    ):
        manager.set_model(
            ModelRole.MAIN,
            "fake",
            "missing",
        )


def test_profile_is_returned_as_copy(
    tmp_path: Path,
) -> None:
    manager = _build_manager(
        tmp_path
    )

    external_profile = manager.profile()

    external_profile.mode = (
        RuntimeMode.MAXIMUM
    )

    assert (
        manager.profile().mode
        == RuntimeMode.AUTO
    )