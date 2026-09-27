from enum import StrEnum


class Capability(StrEnum):
    """
    Security capabilities understood by JARVIS.

    Capabilities describe WHAT category of action a tool
    wants to perform.

    PermissionPolicy independently decides whether each
    capability is:

        ALLOW
        DENY
        REQUIRE_CONFIRMATION
    """

    READ_FILE = "READ_FILE"
    WRITE_FILE = "WRITE_FILE"
    DELETE_FILE = "DELETE_FILE"

    READ_SYSTEM_INFO = "READ_SYSTEM_INFO"

    CALCULATE = "CALCULATE"

    OPEN_APPLICATION = "OPEN_APPLICATION"
    CONTROL_APPLICATION = "CONTROL_APPLICATION"

    # Normal graceful application/window closing.
    #
    # This is intentionally separate from general window
    # control because closing may affect unsaved work.
    CLOSE_APPLICATION = "CLOSE_APPLICATION"

    RUN_COMMAND = "RUN_COMMAND"

    USE_BROWSER = "USE_BROWSER"

    INSTALL_SOFTWARE = "INSTALL_SOFTWARE"

    SEND_EMAIL = "SEND_EMAIL"

    DEPLOY_APPLICATION = "DEPLOY_APPLICATION"