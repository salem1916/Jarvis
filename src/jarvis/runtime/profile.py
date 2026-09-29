from enum import StrEnum

from pydantic import BaseModel, Field


class RuntimeMode(StrEnum):
    """
    High-level intelligence mode visible to normal users.
    """

    AUTO = "auto"
    LOCAL = "local"
    SMART = "smart"
    MAXIMUM = "maximum"


class AgentEngineId(StrEnum):
    """
    Agent orchestration engine.

    AUTO allows JARVIS to choose later.
    """

    AUTO = "auto"
    NATIVE = "native"
    HERMES = "hermes"


class ModelRole(StrEnum):
    """
    Jobs that may use different models.

    A user may leave most roles on AUTO later.
    """

    MAIN = "main"
    WORKER = "worker"
    CODING = "coding"
    RESEARCH = "research"
    LOCAL_FALLBACK = "local_fallback"


class ModelSelection(BaseModel):
    """
    One exact provider/model choice.

    Example:

        provider_id="ollama"
        model_id="qwen3.5:4b"
    """

    provider_id: str = Field(
        min_length=1
    )

    model_id: str = Field(
        min_length=1
    )

    @property
    def key(self) -> str:
        return (
            f"{self.provider_id}:"
            f"{self.model_id}"
        )


class RuntimeProfile(BaseModel):
    """
    Complete AI runtime configuration for JARVIS.

    This contains model identifiers only.

    API credentials belong in a secure credential store and
    must never be persisted inside this profile.
    """

    mode: RuntimeMode = (
        RuntimeMode.AUTO
    )

    agent_engine: AgentEngineId = (
        AgentEngineId.AUTO
    )

    models: dict[
        ModelRole,
        ModelSelection,
    ] = Field(
        default_factory=dict
    )

    def model_for(
        self,
        role: ModelRole,
    ) -> ModelSelection | None:
        """
        Return the configured model for a role.
        """

        return self.models.get(
            role
        )

    def set_model(
        self,
        role: ModelRole,
        selection: ModelSelection,
    ) -> None:
        """
        Configure one runtime model role.
        """

        self.models[
            role
        ] = selection

    def clear_model(
        self,
        role: ModelRole,
    ) -> None:
        """
        Return a role to automatic routing.
        """

        self.models.pop(
            role,
            None,
        )
        