import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


def _default_state_dir() -> Path:
    """
    Return JARVIS's private application-state directory.
    """

    appdata = os.environ.get(
        "APPDATA"
    )

    if appdata:
        return (
            Path(appdata)
            / "Jarvis"
        )

    return (
        Path.home()
        / ".jarvis"
    )


class JarvisSettings(BaseSettings):
    """
    Base JARVIS configuration.

    Secrets may be loaded from environment variables, but
    they are never written into RuntimeProfile.

    Persistence defaults to False for unit-test isolation.
    """

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        extra="ignore",
    )

    workspace_dir: Path = Path(
        "workspace"
    )

    allow_read_file: bool = False
    allow_system_info: bool = False

    # =================================================
    # LOCAL DEFAULT
    # =================================================

    model_provider: str = "ollama"

    openai_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("JARVIS_OPENAI_API_KEY", "OPENAI_API_KEY", "openai_api_key")
    )
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    prefer_cloud_reasoning: bool = True

    ollama_model: str = "qwen3.5:4b"

    ollama_base_url: str = (
        "http://127.0.0.1:11434"
    )

    # =================================================
    # UNIVERSAL MODEL HUB
    # =================================================

    # OpenRouter
    #
    # One account can expose a very large multi-provider
    # model catalog.
    openrouter_api_key: str | None = None

    openrouter_base_url: str = (
        "https://openrouter.ai/api/v1"
    )

    # Groq
    #
    # Intended primarily as JARVIS's very-fast hosted
    # inference option.
    groq_api_key: str | None = None

    groq_base_url: str = (
        "https://api.groq.com/openai/v1"
    )

    # xAI / Grok
    xai_api_key: str | None = None

    xai_base_url: str = (
        "https://api.x.ai/v1"
    )

    # LM Studio
    #
    # Useful on this PC and especially useful when JARVIS is
    # moved to a stronger workstation later.
    lm_studio_enabled: bool = True

    lm_studio_base_url: str = (
        "http://127.0.0.1:1234/v1"
    )

    # -------------------------------------------------
    # CUSTOM OPENAI-COMPATIBLE PROVIDER
    # -------------------------------------------------
    #
    # This is the escape hatch that prevents JARVIS from
    # becoming tied to today's provider list.
    #
    # Examples later:
    #
    #   llama.cpp server
    #   vLLM
    #   SGLang
    #   remote workstation
    #   LAN inference server
    #   future hosted provider
    #
    # Nothing is registered unless base_url is configured.

    custom_provider_id: str = "custom"

    custom_provider_name: str = (
        "Custom OpenAI-compatible"
    )

    custom_provider_base_url: (
        str
        | None
    ) = None

    custom_provider_api_key: (
        str
        | None
    ) = None

    custom_provider_local: bool = False

    # =================================================
    # APPLICATION STATE
    # =================================================

    state_dir: Path = Field(
        default_factory=_default_state_dir
    )

    persist_filesystem_scopes: bool = False

    persist_permission_modes: bool = False

    persist_runtime_profile: bool = False

    persist_action_memory: bool = False

    persist_personal_memory: bool = False


class _EnvJarvisSettings(
    JarvisSettings
):
    """
    Real desktop JARVIS configuration.

    Environment variables and .env may provide credentials.

    Persistent runtime choices are stored separately from
    credentials.
    """

    persist_filesystem_scopes: bool = True

    persist_permission_modes: bool = True

    persist_runtime_profile: bool = True

    persist_action_memory: bool = True

    persist_personal_memory: bool = True

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings() -> JarvisSettings:
    """
    Load real runtime settings.
    """

    return _EnvJarvisSettings()
