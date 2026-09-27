from enum import StrEnum


class Capability(StrEnum):
    """
    Security capabilities understood by JARVIS.

    Each capability represents one category of authority.

    PermissionPolicy independently determines whether each
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

    CLOSE_APPLICATION = "CLOSE_APPLICATION"

    TYPE_TEXT = "TYPE_TEXT"

    KEYBOARD_ACTION = "KEYBOARD_ACTION"

    # Inspect named controls inside a visible application
    # window using Windows UI Automation.
    INSPECT_UI = "INSPECT_UI"

    # Click one resolved named UI element.
    #
    # This deliberately does NOT grant arbitrary mouse
    # coordinates.
    CLICK_UI = "CLICK_UI"

    RUN_COMMAND = "RUN_COMMAND"

    USE_BROWSER = "USE_BROWSER"

    INSTALL_SOFTWARE = "INSTALL_SOFTWARE"

    SEND_EMAIL = "SEND_EMAIL"

    DEPLOY_APPLICATION = "DEPLOY_APPLICATION"