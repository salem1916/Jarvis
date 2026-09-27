from enum import StrEnum


class Capability(StrEnum):
    """
    Security capabilities used by JARVIS tools.

    A tool declares which capability it requires.

    PermissionPolicy then decides whether that
    capability is allowed, denied, or requires
    confirmation.

    This keeps AI reasoning separate from actual
    computer permissions.
    """

    # -------------------------------------------------
    # Filesystem capabilities
    # -------------------------------------------------

    READ_FILE = "READ_FILE"
    WRITE_FILE = "WRITE_FILE"
    DELETE_FILE = "DELETE_FILE"

    # -------------------------------------------------
    # System information
    # -------------------------------------------------

    READ_SYSTEM_INFO = "READ_SYSTEM_INFO"

    # -------------------------------------------------
    # Safe local computation
    # -------------------------------------------------

    # Used by the deterministic calculator tool.
    #
    # This performs local arithmetic only and has
    # no filesystem, network, or application side effects.
    CALCULATE = "CALCULATE"

    # -------------------------------------------------
    # Application / computer control
    # -------------------------------------------------

    OPEN_APPLICATION = "OPEN_APPLICATION"
    CONTROL_APPLICATION = "CONTROL_APPLICATION"

    # -------------------------------------------------
    # More sensitive capabilities
    # -------------------------------------------------

    RUN_COMMAND = "RUN_COMMAND"
    USE_BROWSER = "USE_BROWSER"
    INSTALL_SOFTWARE = "INSTALL_SOFTWARE"

    # -------------------------------------------------
    # External actions
    # -------------------------------------------------

    SEND_EMAIL = "SEND_EMAIL"
    DEPLOY_APPLICATION = "DEPLOY_APPLICATION"