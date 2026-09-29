from typing import cast

from jarvis.agents.native import (
    NativeAgentEngine,
)
from jarvis.core.agent_service import (
    AgentService,
)


class FakeAgentService:
    def __init__(self) -> None:
        self.prompts: list[
            str
        ] = []

    def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
        conversation: object = None,
        confirmation_handler: object = None,
    ) -> str:
        del system_prompt
        del conversation
        del confirmation_handler

        self.prompts.append(
            prompt
        )

        return "native result"


def test_native_engine_wraps_existing_agent_service() -> None:
    service = FakeAgentService()

    engine = NativeAgentEngine(
        cast(
            AgentService,
            service,
        )
    )

    result = engine.run(
        "Hello JARVIS"
    )

    assert (
        result
        == "native result"
    )

    assert service.prompts == [
        "Hello JARVIS"
    ]