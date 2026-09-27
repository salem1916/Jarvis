from enum import StrEnum

from jarvis.security.capabilities import Capability


class PermissionDecision(StrEnum):
    """
    Result of evaluating one JARVIS capability.
    """

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


class PermissionPolicy:
    """
    Deterministic JARVIS capability policy.

    The AI does not control this object.

    A capability may be:

        ALLOW
        DENY
        REQUIRE_CONFIRMATION

    The policy can now also be changed at runtime by the
    trusted JARVIS application layer when the human changes
    a permission setting.
    """

    def __init__(
        self,
        allowed: set[Capability] | None = None,
        require_confirmation: set[Capability] | None = None,
    ) -> None:
        self.allowed = set(
            allowed or set()
        )

        self.require_confirmation = set(
            require_confirmation or set()
        )

        # Confirmation takes precedence if a capability was
        # accidentally supplied to both sets.
        self.allowed.difference_update(
            self.require_confirmation
        )

    def evaluate(
        self,
        capability: Capability,
    ) -> PermissionDecision:
        """
        Evaluate one capability.
        """

        if capability in self.require_confirmation:
            return PermissionDecision.REQUIRE_CONFIRMATION

        if capability in self.allowed:
            return PermissionDecision.ALLOW

        return PermissionDecision.DENY

    def set_decision(
        self,
        capability: Capability,
        decision: PermissionDecision,
    ) -> None:
        """
        Change one capability's effective policy.

        Only trusted application code should call this.

        The AI model never receives direct access to this API.
        """

        # Remove the previous state first so a capability
        # cannot accidentally exist in conflicting sets.
        self.allowed.discard(
            capability
        )

        self.require_confirmation.discard(
            capability
        )

        if decision is PermissionDecision.ALLOW:
            self.allowed.add(
                capability
            )

            return

        if decision is PermissionDecision.REQUIRE_CONFIRMATION:
            self.require_confirmation.add(
                capability
            )

            return

        # DENY requires no set membership.