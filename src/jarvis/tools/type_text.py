import ctypes
from collections.abc import Mapping
from ctypes import wintypes
from typing import ClassVar, Protocol

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.window_catalog import WindowCatalog

# =========================================================
# WINDOWS SENDINPUT CONSTANTS
# =========================================================

_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_INPUT_HARDWARE = 2

_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004

_VK_RETURN = 0x0D
_VK_TAB = 0x09


# =========================================================
# NATIVE WINDOWS INPUT STRUCTURES
# =========================================================
#
# IMPORTANT:
#
# Windows INPUT contains a union of:
#
#     MOUSEINPUT
#     KEYBDINPUT
#     HARDWAREINPUT
#
# Even though JARVIS currently sends keyboard events only,
# the complete union MUST be represented.
#
# Otherwise sizeof(INPUT) is wrong on 64-bit Windows and
# SendInput rejects the request.
# =========================================================


class _MouseInput(ctypes.Structure):
    """
    Native Win32 MOUSEINPUT structure.

    JARVIS does not use this yet.

    It exists here because INPUT's native union size depends
    on its largest member.
    """

    _fields_ = [
        (
            "dx",
            wintypes.LONG,
        ),
        (
            "dy",
            wintypes.LONG,
        ),
        (
            "mouseData",
            wintypes.DWORD,
        ),
        (
            "dwFlags",
            wintypes.DWORD,
        ),
        (
            "time",
            wintypes.DWORD,
        ),
        (
            "dwExtraInfo",
            ctypes.c_size_t,
        ),
    ]


class _KeyboardInput(ctypes.Structure):
    """
    Native Win32 KEYBDINPUT structure.
    """

    _fields_ = [
        (
            "wVk",
            wintypes.WORD,
        ),
        (
            "wScan",
            wintypes.WORD,
        ),
        (
            "dwFlags",
            wintypes.DWORD,
        ),
        (
            "time",
            wintypes.DWORD,
        ),
        (
            "dwExtraInfo",
            ctypes.c_size_t,
        ),
    ]


class _HardwareInput(ctypes.Structure):
    """
    Native Win32 HARDWAREINPUT structure.

    JARVIS does not use hardware input directly, but the
    complete INPUT union must contain this member.
    """

    _fields_ = [
        (
            "uMsg",
            wintypes.DWORD,
        ),
        (
            "wParamL",
            wintypes.WORD,
        ),
        (
            "wParamH",
            wintypes.WORD,
        ),
    ]


class _InputUnion(ctypes.Union):
    """
    Complete native union used by Win32 INPUT.
    """

    _fields_ = [
        (
            "mi",
            _MouseInput,
        ),
        (
            "ki",
            _KeyboardInput,
        ),
        (
            "hi",
            _HardwareInput,
        ),
    ]


class _Input(ctypes.Structure):
    """
    Native Win32 INPUT structure.

    On normal 64-bit Windows this should be 40 bytes.

    The complete union above is critical. A truncated INPUT
    structure causes SendInput to fail.
    """

    _anonymous_ = (
        "union",
    )

    _fields_ = [
        (
            "type",
            wintypes.DWORD,
        ),
        (
            "union",
            _InputUnion,
        ),
    ]


class TextInputBackend(Protocol):
    """
    Platform abstraction for literal keyboard input.
    """

    def type_text(
        self,
        text: str,
    ) -> None:
        ...


class Win32TextInputBackend:
    """
    Send literal text using the real Windows SendInput API.

    Supported:

        normal Unicode text
        newline
        tab

    Not supported:

        Ctrl shortcuts
        Alt shortcuts
        Windows-key shortcuts
        arbitrary key combinations
    """

    def type_text(
        self,
        text: str,
    ) -> None:
        """
        Type literal text into the currently focused window.
        """

        normalized_text = text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        inputs: list[
            _Input
        ] = []

        for character in normalized_text:
            # ---------------------------------------------
            # ENTER / NEWLINE
            # ---------------------------------------------

            if character == "\n":
                inputs.extend(
                    self._virtual_key_inputs(
                        _VK_RETURN
                    )
                )

                continue

            # ---------------------------------------------
            # TAB
            # ---------------------------------------------

            if character == "\t":
                inputs.extend(
                    self._virtual_key_inputs(
                        _VK_TAB
                    )
                )

                continue

            # ---------------------------------------------
            # Reject hidden control characters.
            # ---------------------------------------------

            if ord(
                character
            ) < 32:
                raise ValueError(
                    "Text contains an unsupported control "
                    "character."
                )

            # ---------------------------------------------
            # UNICODE
            #
            # KEYEVENTF_UNICODE accepts UTF-16 code units.
            #
            # Encoding each Python character to UTF-16LE also
            # correctly handles characters represented through
            # surrogate pairs.
            # ---------------------------------------------

            encoded = character.encode(
                "utf-16-le"
            )

            for index in range(
                0,
                len(
                    encoded
                ),
                2,
            ):
                code_unit = int.from_bytes(
                    encoded[
                        index:
                        index + 2
                    ],
                    byteorder="little",
                )

                inputs.extend(
                    self._unicode_inputs(
                        code_unit
                    )
                )

        if not inputs:
            return

        # -------------------------------------------------
        # Build one contiguous native INPUT array.
        # -------------------------------------------------

        input_array_type = (
            _Input
            * len(
                inputs
            )
        )

        input_array = input_array_type(
            *inputs
        )

        # Clear any previous Win32 error value before calling
        # SendInput so diagnostics are not misleading.
        ctypes.set_last_error(
            0
        )

        sent = ctypes.windll.user32.SendInput(  # type: ignore[attr-defined]
            len(
                inputs
            ),
            input_array,
            ctypes.sizeof(
                _Input
            ),
        )

        if sent != len(
            inputs
        ):
            error_code = ctypes.get_last_error()

            raise OSError(
                "Windows did not accept all requested keyboard "
                "input events. "
                f"Accepted {sent} of {len(inputs)} events. "
                f"Win32 error code: {error_code}. "
                f"INPUT size: {ctypes.sizeof(_Input)} bytes."
            )

    @staticmethod
    def _unicode_inputs(
        code_unit: int,
    ) -> tuple[
        _Input,
        _Input,
    ]:
        """
        Create key-down and key-up events for one UTF-16
        Unicode code unit.
        """

        down = _Input(
            type=_INPUT_KEYBOARD,
            ki=_KeyboardInput(
                wVk=0,
                wScan=code_unit,
                dwFlags=_KEYEVENTF_UNICODE,
                time=0,
                dwExtraInfo=0,
            ),
        )

        up = _Input(
            type=_INPUT_KEYBOARD,
            ki=_KeyboardInput(
                wVk=0,
                wScan=code_unit,
                dwFlags=(
                    _KEYEVENTF_UNICODE
                    | _KEYEVENTF_KEYUP
                ),
                time=0,
                dwExtraInfo=0,
            ),
        )

        return (
            down,
            up,
        )

    @staticmethod
    def _virtual_key_inputs(
        virtual_key: int,
    ) -> tuple[
        _Input,
        _Input,
    ]:
        """
        Create key-down and key-up events for one explicitly
        permitted virtual key.

        Currently:

            Enter
            Tab
        """

        down = _Input(
            type=_INPUT_KEYBOARD,
            ki=_KeyboardInput(
                wVk=virtual_key,
                wScan=0,
                dwFlags=0,
                time=0,
                dwExtraInfo=0,
            ),
        )

        up = _Input(
            type=_INPUT_KEYBOARD,
            ki=_KeyboardInput(
                wVk=virtual_key,
                wScan=0,
                dwFlags=_KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            ),
        )

        return (
            down,
            up,
        )


class TypeTextTool(Tool):
    """
    Type literal text into one specific visible Windows window.

    SECURITY MODEL

    The model supplies only:

        window title
        literal text

    Trusted JARVIS code:

        discovers the real window
        resolves the title
        focuses that window
        sends literal keyboard text

    This tool does NOT expose arbitrary hotkeys or commands.
    """

    name = "type_text"

    description = (
        "Type literal text into a specific visible Windows "
        "application window. JARVIS resolves and focuses the "
        "requested window before typing. Newlines and tabs are "
        "supported. Arbitrary keyboard shortcuts are not "
        "supported. Use list_open_windows if the exact window "
        "title is unknown."
    )

    required_capability = Capability.TYPE_TEXT

    parameters_schema: ClassVar[
        dict[str, object]
    ] = {
        "type": "object",
        "properties": {
            "window": {
                "type": "string",
                "description": (
                    "Visible window title or a unique portion "
                    "of the title."
                ),
            },
            "text": {
                "type": "string",
                "description": (
                    "Exact literal text to type."
                ),
            },
        },
        "required": [
            "window",
            "text",
        ],
        "additionalProperties": False,
    }

    MAX_TEXT_LENGTH = 10_000

    def __init__(
        self,
        catalog: WindowCatalog,
        text_backend: TextInputBackend,
    ) -> None:
        self.catalog = catalog
        self.text_backend = text_backend

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Focus one resolved window and type literal text.
        """

        raw_window = arguments.get(
            "window"
        )

        raw_text = arguments.get(
            "text"
        )

        if not isinstance(
            raw_window,
            str,
        ):
            raise TypeError(
                "'window' must be a string."
            )

        if not isinstance(
            raw_text,
            str,
        ):
            raise TypeError(
                "'text' must be a string."
            )

        if not raw_text:
            raise ValueError(
                "'text' cannot be empty."
            )

        if len(
            raw_text
        ) > self.MAX_TEXT_LENGTH:
            raise ValueError(
                "Text is too long for one typing action."
            )

        # Validate everything before focusing another window.
        for character in raw_text:
            if (
                ord(
                    character
                ) < 32
                and character
                not in {
                    "\n",
                    "\r",
                    "\t",
                }
            ):
                raise ValueError(
                    "Text contains an unsupported control "
                    "character."
                )

        # -------------------------------------------------
        # Resolve the window using trusted Windows discovery.
        # -------------------------------------------------

        entry = self.catalog.resolve(
            raw_window
        )

        # -------------------------------------------------
        # Focus it before sending keyboard input.
        # -------------------------------------------------

        self.catalog.backend.focus(
            entry.handle
        )

        # -------------------------------------------------
        # Send literal text.
        # -------------------------------------------------

        self.text_backend.type_text(
            raw_text
        )

        return {
            "ok": True,
            "action": "text_typed",
            "window": entry.title,
            "characters": len(
                raw_text
            ),
        }