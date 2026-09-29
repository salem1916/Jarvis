import json
from pathlib import Path

import pytest

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


def test_missing_profile_returns_defaults(
    tmp_path: Path,
) -> None:
    store = RuntimeProfileStore(
        tmp_path
        / "runtime_profile.json"
    )

    profile = store.load()

    assert (
        profile.mode
        == RuntimeMode.AUTO
    )

    assert (
        profile.agent_engine
        == AgentEngineId.AUTO
    )


def test_profile_round_trip(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "state"
        / "runtime_profile.json"
    )

    store = RuntimeProfileStore(
        path
    )

    profile = RuntimeProfile(
        mode=RuntimeMode.SMART,
        agent_engine=(
            AgentEngineId.HERMES
        ),
        models={
            ModelRole.MAIN: (
                ModelSelection(
                    provider_id="groq",
                    model_id="smart-model",
                )
            ),
            ModelRole.LOCAL_FALLBACK: (
                ModelSelection(
                    provider_id="ollama",
                    model_id="qwen3.5:4b",
                )
            ),
        },
    )

    store.save(
        profile
    )

    loaded = store.load()

    assert loaded == profile


def test_save_creates_parent_directory(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "nested"
        / "state"
        / "runtime_profile.json"
    )

    store = RuntimeProfileStore(
        path
    )

    store.save(
        RuntimeProfile()
    )

    assert path.exists()


def test_unsupported_profile_version_is_rejected(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "runtime_profile.json"
    )

    path.write_text(
        json.dumps(
            {
                "version": 999,
                "profile": {},
            }
        ),
        encoding="utf-8",
    )

    store = RuntimeProfileStore(
        path
    )

    with pytest.raises(
        ValueError,
        match=(
            "Unsupported runtime "
            "profile version"
        ),
    ):
        store.load()