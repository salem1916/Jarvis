from dataclasses import dataclass
from typing import Protocol

from pywinauto import Desktop


def _normalize_ui_text(
    value: str,
) -> str:
    """
    Normalize human-visible UI text.

    Windows UI controls sometimes expose mnemonic markers:

        &Save

    This should still match:

        Save
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
    One UI element discovered through Windows UI Automation.

    locator is internal trusted JARVIS state.

    It is never exposed to the AI model.
    """

    locator: str
    name: str
    control_type: str
    enabled: bool


class UiAutomationBackend(Protocol):
    """
    Platform abstraction for Windows UI Automation.
    """

    def list_elements(
        self,
        window_handle: int,
    ) -> tuple[UiElementEntry, ...]:
        ...

    def click(
        self,
        window_handle: int,
        locator: str,
    ) -> None:
        ...


class PywinautoUiAutomationBackend:
    """
    Real Windows UI Automation backend using pywinauto.

    The model never supplies screen coordinates or internal
    UI Automation identifiers.
    """

    MAX_ELEMENTS = 200

    def list_elements(
        self,
        window_handle: int,
    ) -> tuple[UiElementEntry, ...]:
        """
        Enumerate named visible descendants of one trusted
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
                # UI trees can change while being enumerated.
                #
                # A disappearing individual element should not
                # invalidate the entire read-only inspection.
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
        Click one internally resolved UI element.
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

        wrapper.click_input()


class UiElementCatalog:
    """
    Trusted resolver for controls inside one Windows window.

    The model supplies only human-readable names.

    Internal locators remain trusted state.
    """

    def __init__(
        self,
        backend: UiAutomationBackend,
    ) -> None:
        self.backend = backend

    def entries(
        self,
        window_handle: int,
    ) -> tuple[UiElementEntry, ...]:
        """
        Return current named UI elements for one window.
        """

        return self.backend.list_elements(
            window_handle
        )

    def matching_entries(
        self,
        window_handle: int,
        requested_name: str,
        requested_control_type: str | None = None,
    ) -> tuple[UiElementEntry, ...]:
        """
        Return deterministic matching UI elements.

        Exact name matches are preferred over partial matches.

        Multiple matches are returned to the caller instead of
        silently choosing one.
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

        candidates = tuple(
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
        )

        exact_matches = tuple(
            entry
            for entry in candidates
            if (
                _normalize_ui_text(
                    entry.name
                )
                == normalized_name
            )
        )

        if exact_matches:
            return exact_matches

        return tuple(
            entry
            for entry in candidates
            if normalized_name
            in _normalize_ui_text(
                entry.name
            )
        )

    def resolve(
        self,
        window_handle: int,
        requested_name: str,
        requested_control_type: str | None = None,
    ) -> UiElementEntry:
        """
        Resolve exactly one UI element inside one window.
        """

        matches = self.matching_entries(
            window_handle=window_handle,
            requested_name=requested_name,
            requested_control_type=requested_control_type,
        )

        if len(
            matches
        ) == 1:
            return matches[0]

        if len(
            matches
        ) > 1:
            descriptions = ", ".join(
                (
                    f"{entry.name} "
                    f"({entry.control_type})"
                )
                for entry
                in matches[:10]
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