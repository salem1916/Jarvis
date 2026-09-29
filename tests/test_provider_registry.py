import pytest

from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from jarvis.models.provider_registry import (
    ProviderRegistry,
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


def test_registry_creates_selected_provider() -> None:
    registry = ProviderRegistry()

    registry.register(
        "fake",
        lambda model_id: FakeProvider(
            model_id
        ),
    )

    provider = registry.create(
        "fake",
        "smart-model",
    )

    assert isinstance(
        provider,
        FakeProvider,
    )

    assert (
        provider.model
        == "smart-model"
    )


def test_duplicate_provider_is_rejected() -> None:
    registry = ProviderRegistry()

    registry.register(
        "fake",
        lambda model_id: FakeProvider(
            model_id
        ),
    )

    with pytest.raises(
        ValueError,
        match="already registered",
    ):
        registry.register(
            "fake",
            lambda model_id: FakeProvider(
                model_id
            ),
        )


def test_unknown_provider_is_rejected() -> None:
    registry = ProviderRegistry()

    with pytest.raises(
        KeyError,
        match="Unknown model provider",
    ):
        registry.create(
            "missing",
            "model",
        )