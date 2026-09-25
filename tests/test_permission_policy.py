from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision, PermissionPolicy


def test_allowed_capability_is_allowed():
    policy = PermissionPolicy(
        allowed={Capability.READ_FILE},
    )

    result = policy.evaluate(Capability.READ_FILE)

    assert result == PermissionDecision.ALLOW


def test_unknown_capability_is_denied_by_default():
    policy = PermissionPolicy()

    result = policy.evaluate(Capability.DELETE_FILE)

    assert result == PermissionDecision.DENY


def test_sensitive_capability_can_require_confirmation():
    policy = PermissionPolicy(
        require_confirmation={Capability.SEND_EMAIL},
    )

    result = policy.evaluate(Capability.SEND_EMAIL)

    assert result == PermissionDecision.REQUIRE_CONFIRMATION
    