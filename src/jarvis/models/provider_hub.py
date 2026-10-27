from collections.abc import Callable
from dataclasses import dataclass

from jarvis.core.config import JarvisSettings
from jarvis.models.base import ModelProvider
from jarvis.models.catalog import (
    ModelCatalog,
    ModelLocation,
    ProviderDefinition,
)
from jarvis.models.discovery import (
    ModelDiscoveryService,
)
from jarvis.models.openai_compatible import (
    OpenAICompatibleProvider,
)
from jarvis.models.openai_compatible_discovery import (
    OpenAICompatibleDiscoveryService,
)
from jarvis.models.provider_registry import (
    ProviderRegistry,
)


@dataclass(
    frozen=True,
    slots=True,
)
class ProviderRuntimeSpec:
    """
    Runtime description of one OpenAI-compatible provider.

    Secrets exist here only in memory.

    They are never copied into ModelCatalog or RuntimeProfile.
    """

    provider_id: str
    display_name: str

    base_url: str

    location: ModelLocation

    api_key: str | None = None

    requires_api_key: bool = True

    enabled: bool = True

    @property
    def configured(
        self,
    ) -> bool:
        """
        Return whether JARVIS has enough configuration to use
        this provider.
        """

        if not self.enabled:
            return False

        if self.requires_api_key:
            return bool(
                self.api_key
                and self.api_key.strip()
            )

        return True

    @property
    def runtime_api_key(
        self,
    ) -> str:
        """
        Return the credential passed to the generic provider.

        Local OpenAI-compatible servers often ignore the
        Authorization value but OpenAICompatibleProvider keeps
        one uniform interface, so use a harmless local value.
        """

        if (
            self.api_key
            and self.api_key.strip()
        ):
            return self.api_key.strip()

        if not self.requires_api_key:
            return "local"

        raise RuntimeError(
            "Provider is not configured: "
            f"{self.provider_id}"
        )


def _provider_factory(
    spec: ProviderRuntimeSpec,
) -> Callable[
    [str],
    ModelProvider,
]:
    """
    Build a ProviderRegistry-compatible factory.
    """

    def factory(
        model_id: str,
    ) -> ModelProvider:
        return OpenAICompatibleProvider(
            provider_name=(
                spec.provider_id
            ),
            model=model_id,
            base_url=spec.base_url,
            api_key=spec.runtime_api_key,
        )

    return factory


def builtin_provider_specs(
    settings: JarvisSettings,
) -> tuple[
    ProviderRuntimeSpec,
    ...,
]:
    """
    Return built-in universal-provider configurations.

    Adding another OpenAI-compatible provider later should
    normally require one ProviderRuntimeSpec rather than a new
    architecture.
    """

    specs: list[
        ProviderRuntimeSpec
    ] = [
        ProviderRuntimeSpec(
            provider_id="openai",
            display_name="OpenAI / ChatGPT API",
            base_url=settings.openai_base_url,
            location=ModelLocation.CLOUD,
            api_key=settings.openai_api_key,
        ),
        ProviderRuntimeSpec(
            provider_id="openrouter",
            display_name="OpenRouter",
            base_url=(
                settings.openrouter_base_url
            ),
            location=ModelLocation.CLOUD,
            api_key=(
                settings.openrouter_api_key
            ),
            requires_api_key=True,
        ),
        ProviderRuntimeSpec(
            provider_id="groq",
            display_name="Groq",
            base_url=(
                settings.groq_base_url
            ),
            location=ModelLocation.CLOUD,
            api_key=settings.groq_api_key,
            requires_api_key=True,
        ),
        ProviderRuntimeSpec(
            provider_id="xai",
            display_name="xAI / Grok",
            base_url=settings.xai_base_url,
            location=ModelLocation.CLOUD,
            api_key=settings.xai_api_key,
            requires_api_key=True,
        ),
        ProviderRuntimeSpec(
            provider_id="lm_studio",
            display_name="LM Studio",
            base_url=(
                settings.lm_studio_base_url
            ),
            location=ModelLocation.LOCAL,
            requires_api_key=False,
            enabled=(
                settings.lm_studio_enabled
            ),
        ),
    ]

    custom_base_url = (
        settings.custom_provider_base_url
    )

    if (
        custom_base_url is not None
        and custom_base_url.strip()
    ):
        specs.append(
            ProviderRuntimeSpec(
                provider_id=(
                    settings.custom_provider_id
                ),
                display_name=(
                    settings.custom_provider_name
                ),
                base_url=(
                    custom_base_url.strip()
                ),
                location=(
                    ModelLocation.LOCAL
                    if settings.custom_provider_local
                    else ModelLocation.CLOUD
                ),
                api_key=(
                    settings.custom_provider_api_key
                ),
                requires_api_key=(
                    not settings.custom_provider_local
                ),
            )
        )

    return tuple(
        specs
    )


def register_provider_hub(
    *,
    settings: JarvisSettings,
    catalog: ModelCatalog,
    provider_registry: ProviderRegistry,
) -> tuple[
    ModelDiscoveryService,
    ...,
]:
    """
    Register all universal-provider metadata and runtime
    factories.

    Provider metadata is registered even when credentials are
    missing so the future Models UI can show:

        OpenRouter    Not connected
        Groq          Not connected
        xAI           Not connected
        LM Studio     Available locally

    Runtime factories and live discovery are registered only
    when a provider is actually configured.

    No network calls occur here.
    """

    discovery_services: list[
        ModelDiscoveryService
    ] = []

    for spec in builtin_provider_specs(
        settings
    ):
        catalog.register_provider(
            ProviderDefinition(
                provider_id=(
                    spec.provider_id
                ),
                display_name=(
                    spec.display_name
                ),
                location=spec.location,
                requires_api_key=(
                    spec.requires_api_key
                ),
                supports_model_discovery=True,
                supports_model_installation=False,
                openai_compatible=True,
            )
        )

        if not spec.configured:
            continue

        provider_registry.register(
            spec.provider_id,
            _provider_factory(
                spec
            ),
        )

        discovery_services.append(
            OpenAICompatibleDiscoveryService(
                provider_id=(
                    spec.provider_id
                ),
                base_url=spec.base_url,
                location=spec.location,
                api_key=(
                    spec.runtime_api_key
                ),
            )
        )

    return tuple(
        discovery_services
    )
