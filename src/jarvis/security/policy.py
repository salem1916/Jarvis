from enum import StrEnum

from jarvis.security.capabilities import Capability


class PermissionDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


class PermissionPolicy:
    def __init__(
        self,
        allowed: set[Capability] | None = None,
        require_confirmation: set[Capability] | None = None,
    ) -> None:
        self.allowed = allowed or set()
        self.require_confirmation = require_confirmation or set()

    def evaluate(self, capability: Capability) -> PermissionDecision:
        if capability in self.require_confirmation:
            return PermissionDecision.REQUIRE_CONFIRMATION

        if capability in self.allowed:
            return PermissionDecision.ALLOW

        return PermissionDecision.DENY