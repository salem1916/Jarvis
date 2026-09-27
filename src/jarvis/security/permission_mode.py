from enum import StrEnum

from jarvis.security.policy import PermissionDecision


class PermissionMode(StrEnum):
    """
    User-facing permission modes.

    DENY
        Never allow the capability.

    ASK
        Require explicit human approval every time.

    ALLOW_SESSION
        Allow automatically until JARVIS is closed.

        This mode is deliberately NOT persisted.

    ALWAYS_ALLOW
        Allow automatically and remember the choice
        across JARVIS restarts.
    """

    DENY = "deny"
    ASK = "ask"
    ALLOW_SESSION = "allow_session"
    ALWAYS_ALLOW = "always_allow"

    def to_decision(
        self,
    ) -> PermissionDecision:
        """
        Convert the user-facing mode into the actual
        security-engine decision.
        """

        if self is PermissionMode.DENY:
            return PermissionDecision.DENY

        if self is PermissionMode.ASK:
            return PermissionDecision.REQUIRE_CONFIRMATION

        # Both session and persistent automatic access are
        # ALLOW from PermissionPolicy's point of view.
        #
        # Their persistence behavior is handled separately.
        return PermissionDecision.ALLOW