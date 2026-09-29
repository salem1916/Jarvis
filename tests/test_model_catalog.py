import pytest

from jarvis.models.catalog import (
    ModelCatalog,
    ModelDefinition,
    ModelLocation,
    ProviderDefinition,
)


def test_catalog_registers_provider_and_model() -> None:
    catalog = ModelCatalog()

    catalog.register_provider(
        ProviderDefinition(
            provider_id="ollama",
            display_name="Ollama",
            location=ModelLocation.LOCAL,
            supports_model_discovery=True,
            supports_model_installation=True,
        )
    )

    catalog.register_model(
        ModelDefinition(
            provider_id="ollama",
            model_id="qwen3.5:4b",
            display_name="Qwen 3.5 4B",
            location=ModelLocation.LOCAL,
            supports_tools=True,
            installable=True,
            installed=True,
        )
    )

    model = catalog.model(
        "ollama",
        "qwen3.5:4b",
    )

    assert (
        model.provider_id
        == "ollama"
    )

    assert (
        model.model_id
        == "qwen3.5:4b"
    )

    assert model.installed


def test_model_requires_registered_provider() -> None:
    catalog = ModelCatalog()

    with pytest.raises(
        ValueError,
        match=(
            "Model provider "
            "is not registered"
        ),
    ):
        catalog.register_model(
            ModelDefinition(
                provider_id="missing",
                model_id="example",
                display_name="Example",
                location=(
                    ModelLocation.CLOUD
                ),
            )
        )


def test_catalog_filters_models_by_provider() -> None:
    catalog = ModelCatalog()

    catalog.register_provider(
        ProviderDefinition(
            provider_id="ollama",
            display_name="Ollama",
            location=ModelLocation.LOCAL,
        )
    )

    catalog.register_provider(
        ProviderDefinition(
            provider_id="cloud",
            display_name="Cloud",
            location=ModelLocation.CLOUD,
        )
    )

    catalog.register_model(
        ModelDefinition(
            provider_id="ollama",
            model_id="local-model",
            display_name="Local Model",
            location=ModelLocation.LOCAL,
        )
    )

    catalog.register_model(
        ModelDefinition(
            provider_id="cloud",
            model_id="cloud-model",
            display_name="Cloud Model",
            location=ModelLocation.CLOUD,
        )
    )

    models = (
        catalog.models_for_provider(
            "ollama"
        )
    )

    assert len(
        models
    ) == 1

    assert (
        models[0].model_id
        == "local-model"
    )