from enum import StrEnum


class Capability(StrEnum):
    """
    Security capabilities understood by JARVIS.

    Each capability describes a category of action.

    PermissionPolicy independently decides whether it is:

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

    CLOSE_APPLICATION = "CLOSE_APPLICATION"

    # Literal text insertion only.
    TYPE_TEXT = "TYPE_TEXT"

    # Trusted named keyboard actions such as Ctrl+S,
    # Ctrl+C, Enter, Escape, etc.
    #
    # This is deliberately separate from TYPE_TEXT because
    # shortcuts may trigger application behavior.
    KEYBOARD_ACTION = "KEYBOARD_ACTION"

    RUN_COMMAND = "RUN_COMMAND"

    USE_BROWSER = "USE_BROWSER"

    INSTALL_SOFTWARE = "INSTALL_SOFTWARE"

    SEND_EMAIL = "SEND_EMAIL"

    DEPLOY_APPLICATION = "DEPLOY_APPLICATION"