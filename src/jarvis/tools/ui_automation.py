from dataclasses import dataclass
from typing import Protocol

from pywinauto import Desktop


def _normalize_ui_text(
    value: str,
) -> str:
    """
    Normalize human-visible UI text.

    Windows controls sometimes use ampersands for keyboard
    mnemonics, for example:

        "&Save"

    The user/model should still be able to request:

        "Save"
    """

    return " ".join(
        value
        .replace(
            "&",
            "",
        )
        .strip()
        .casefold()
        .split()
    )


@dataclass(
    frozen=True,
    slots=True,
)
class UiElementEntry:
    """
    One UI element discovered through trusted Windows
    UI Automation.

    locator is internal trusted state.

    It is deliberately NOT returned to the AI model.
    """

    locator: str
    name: str
    control_type: str
    enabled: bool


class UiAutomationBackend(Protocol):
    """
    Platform abstraction for UI Automation.

    Tests use a fake implementation.

    The real desktop uses PywinautoUiAutomationBackend.
    """

    def list_elements(
        self,
        window_handle: int,
    ) -> tuple[
        UiElementEntry,
        ...,
    ]:
        ...

    def click(
        self,
        window_handle: int,
        locator: str,
    ) -> None:
        ...


class PywinautoUiAutomationBackend:
    """
    Windows UI Automation implementation backed by
    pywinauto's UIA backend.

    JARVIS discovers real UI controls rather than allowing
    the AI to invent screen coordinates.
    """

    MAX_ELEMENTS = 200

    def list_elements(
        self,
        window_handle: int,
    ) -> tuple[
        UiElementEntry,
        ...,
    ]:
        """
        Enumerate visible named descendants of one trusted
        top-level window.
        """

        root = Desktop(
            backend="uia"
        ).window(
            handle=window_handle
        )

        descendants = root.descendants()

        elements: list[
            UiElementEntry
        ] = []

        for index, wrapper in enumerate(
            descendants
        ):
            try:
                if not wrapper.is_visible():
                    continue

                element_info = wrapper.element_info

                raw_name = getattr(
                    element_info,
                    "name",
                    "",
                )

                raw_control_type = getattr(
                    element_info,
                    "control_type",
                    "",
                )

                name = (
                    raw_name.strip()
                    if isinstance(
                        raw_name,
                        str,
                    )
                    else ""
                )

                control_type = (
                    raw_control_type.strip()
                    if isinstance(
                        raw_control_type,
                        str,
                    )
                    else ""
                )

                # First safe version exposes named controls
                # only. This prevents large amounts of useless
                # unnamed implementation detail from reaching
                # the model.
                if not name:
                    continue

                enabled = bool(
                    wrapper.is_enabled()
                )

                elements.append(
                    UiElementEntry(
                        locator=str(
                            index
                        ),
                        name=name,
                        control_type=(
                            control_type
                            or "Unknown"
                        ),
                        enabled=enabled,
                    )
                )

                if (
                    len(
                        elements
                    )
                    >= self.MAX_ELEMENTS
                ):
                    break

            except (
                RuntimeError,
                OSError,
            ):
                # UI trees can change while being inspected.
                #
                # A disappearing individual control should not
                # prevent inspection of the rest of the window.
                continue

        return tuple(
            elements
        )

    def click(
        self,
        window_handle: int,
        locator: str,
    ) -> None:
        """
        Click one element previously resolved from the current
        trusted UI tree.

        locator is generated internally by JARVIS.
        """

        try:
            index = int(
                locator
            )

        except ValueError as exc:
            raise ValueError(
                "Invalid internal UI element locator."
            ) from exc

        root = Desktop(
            backend="uia"
        ).window(
            handle=window_handle
        )

        descendants = root.descendants()

        if (
            index < 0
            or index >= len(
                descendants
            )
        ):
            raise ValueError(
                "The selected UI element no longer exists."
            )

        wrapper = descendants[
            index
        ]

        if not wrapper.is_visible():
            raise ValueError(
                "The selected UI element is no longer visible."
            )

        if not wrapper.is_enabled():
            raise ValueError(
                "The selected UI element is disabled."
            )

        # click_input derives coordinates from the actual
        # UI Automation element.
        #
        # The model never supplies X/Y coordinates.
        wrapper.click_input()


class UiElementCatalog:
    """
    Trusted resolver for named UI elements.

    Resolution order:

        exact name + optional type
            ↓
        unique partial name + optional type
            ↓
        reject ambiguity
    """

    def __init__(
        self,
        backend: UiAutomationBackend,
    ) -> None:
        self.backend = backend

    def entries(
        self,
        window_handle: int,
    ) -> tuple[
        UiElementEntry,
        ...,
    ]:
        return self.backend.list_elements(
            window_handle
        )

    def resolve(
        self,
        window_handle: int,
        requested_name: str,
        requested_control_type: str | None = None,
    ) -> UiElementEntry:
        """
        Resolve one UI element deterministically.
        """

        normalized_name = _normalize_ui_text(
            requested_name
        )

        if not normalized_name:
            raise ValueError(
                "UI element name cannot be empty."
            )

        normalized_type = (
            _normalize_ui_text(
                requested_control_type
            )
            if requested_control_type
            else None
        )

        candidates = [
            entry
            for entry in self.entries(
                window_handle
            )
            if (
                normalized_type is None
                or _normalize_ui_text(
                    entry.control_type
                )
                == normalized_type
            )
        ]

        # -------------------------------------------------
        # Exact match first.
        # -------------------------------------------------

        exact_matches = [
            entry
            for entry in candidates
            if (
                _normalize_ui_text(
                    entry.name
                )
                == normalized_name
            )
        ]

        if len(
            exact_matches
        ) == 1:
            return exact_matches[0]

        if len(
            exact_matches
        ) > 1:
            raise ValueError(
                "UI element name is ambiguous. "
                "Specify the control type as well."
            )

        # -------------------------------------------------
        # Then unique partial match.
        # -------------------------------------------------

        partial_matches = [
            entry
            for entry in candidates
            if normalized_name
            in _normalize_ui_text(
                entry.name
            )
        ]

        if len(
            partial_matches
        ) == 1:
            return partial_matches[0]

        if len(
            partial_matches
        ) > 1:
            descriptions = ", ".join(
                (
                    f"{entry.name} "
                    f"({entry.control_type})"
                )
                for entry
                in partial_matches[:10]
            )

            raise ValueError(
                "UI element name is ambiguous. "
                f"Matches: {descriptions}."
            )

        raise ValueError(
            "No visible UI element matched "
            f"'{requested_name}'. "
            "Use list_ui_elements to inspect the current "
            "window controls."
        )