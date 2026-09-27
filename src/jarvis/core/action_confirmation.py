from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from jarvis.security.capabilities import Capability


@dataclass(
    frozen=True,
    slots=True,
)
class ActionConfirmationRequest:
    """
    Exact action JARVIS wants the user to approve.

    Confirmation is bound to one immediate tool request.

    Approving this object does NOT permanently enable the
    capability and does NOT approve future actions.
    """

    tool_name: str
    capability: Capability
    arguments: Mapping[str, object]


class ActionConfirmationHandler(Protocol):
    """
    Interface implemented by whichever JARVIS frontend
    is responsible for asking the human.

    Later implementations:

        Desktop UI
            -> confirmation dialog

        CLI
            -> terminal y/n prompt

        Remote dashboard
            -> approval card
    """

    def confirm(
        self,
        request: ActionConfirmationRequest,
    ) -> bool:
        """
        Return True only after explicit user approval.
        """
        ...


class ActionDeclinedError(RuntimeError):
    """
    Raised when the user explicitly rejects an action.
    """