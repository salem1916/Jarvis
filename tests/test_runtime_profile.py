from jarvis.runtime.profile import (
    AgentEngineId,
    ModelRole,
    ModelSelection,
    RuntimeMode,
    RuntimeProfile,
)


def test_runtime_profile_defaults_to_auto() -> None:
    profile = RuntimeProfile()

    assert (
        profile.mode
        == RuntimeMode.AUTO
    )

    assert (
        profile.agent_engine
        == AgentEngineId.AUTO
    )


def test_runtime_profile_can_assign_model_roles() -> None:
    profile = RuntimeProfile()

    selection = ModelSelection(
        provider_id="ollama",
        model_id="qwen3.5:4b",
    )

    profile.set_model(
        ModelRole.LOCAL_FALLBACK,
        selection,
    )

    assert (
        profile.model_for(
            ModelRole.LOCAL_FALLBACK
        )
        == selection
    )


def test_runtime_profile_can_clear_model_role() -> None:
    profile = RuntimeProfile(
        models={
            ModelRole.MAIN: (
                ModelSelection(
                    provider_id="cloud",
                    model_id="smart-model",
                )
            )
        }
    )

    profile.clear_model(
        ModelRole.MAIN
    )

    assert (
        profile.model_for(
            ModelRole.MAIN
        )
        is None
    )


def test_runtime_profile_keeps_engine_and_model_separate() -> None:
    profile = RuntimeProfile(
        mode=RuntimeMode.SMART,
        agent_engine=(
            AgentEngineId.HERMES
        ),
        models={
            ModelRole.MAIN: (
                ModelSelection(
                    provider_id="groq",
                    model_id="example-model",
                )
            )
        },
    )

    assert (
        profile.agent_engine
        == AgentEngineId.HERMES
    )

    main = profile.model_for(
        ModelRole.MAIN
    )

    assert main is not None

    assert (
        main.provider_id
        == "groq"
    )