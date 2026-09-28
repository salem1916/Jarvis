from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools.click_ui_element import ClickUiElementTool
from jarvis.tools.list_ui_elements import ListUiElementsTool
from jarvis.tools.ui_automation import (
    UiElementCatalog,
    UiElementEntry,
)
from jarvis.tools.window_catalog import (
    WindowCatalog,
    WindowEntry,
)


class FakeWindowBackend:
    def __init__(
        self,
        windows: tuple[
            WindowEntry,
            ...,
        ],
    ) -> None:
        self.windows = windows

        self.focused: list[
            int
        ] = []

    def list_windows(
        self,
    ) -> tuple[
        WindowEntry,
        ...,
    ]:
        return self.windows

    def focus(
        self,
        handle: int,
    ) -> None:
        self.focused.append(
            handle
        )

    def minimize(
        self,
        handle: int,
    ) -> None:
        del handle

    def maximize(
        self,
        handle: int,
    ) -> None:
        del handle

    def restore(
        self,
        handle: int,
    ) -> None:
        del handle


class FakeUiBackend:
    """
    UI elements are stored per real window handle.

    This lets us test duplicate top-level window titles.
    """

    def __init__(
        self,
        elements_by_window: dict[
            int,
            tuple[
                UiElementEntry,
                ...,
            ],
        ],
    ) -> None:
        self.elements_by_window = elements_by_window

        self.clicked: list[
            tuple[
                int,
                str,
            ]
        ] = []

    def list_elements(
        self,
        window_handle: int,
    ) -> tuple[
        UiElementEntry,
        ...,
    ]:
        return self.elements_by_window.get(
            window_handle,
            (),
        )

    def click(
        self,
        window_handle: int,
        locator: str,
    ) -> None:
        self.clicked.append(
            (
                window_handle,
                locator,
            )
        )


def test_list_ui_elements_uses_inspect_capability(
    tmp_path: Path,
) -> None:
    del tmp_path

    tool = ListUiElementsTool(
        window_catalog=WindowCatalog(
            FakeWindowBackend(
                ()
            )
        ),
        ui_catalog=UiElementCatalog(
            FakeUiBackend(
                {}
            )
        ),
    )

    assert (
        tool.required_capability
        is Capability.INSPECT_UI
    )


def test_click_ui_element_uses_separate_capability(
    tmp_path: Path,
) -> None:
    del tmp_path

    tool = ClickUiElementTool(
        window_catalog=WindowCatalog(
            FakeWindowBackend(
                ()
            )
        ),
        ui_catalog=UiElementCatalog(
            FakeUiBackend(
                {}
            )
        ),
    )

    assert (
        tool.required_capability
        is Capability.CLICK_UI
    )


def test_list_ui_elements_hides_internal_locator(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=5,
                title="Save As",
            ),
        )
    )

    ui_backend = FakeUiBackend(
        {
            5: (
                UiElementEntry(
                    locator="secret-internal-id",
                    name="Save",
                    control_type="Button",
                    enabled=True,
                ),
            )
        }
    )

    tool = ListUiElementsTool(
        window_catalog=WindowCatalog(
            window_backend
        ),
        ui_catalog=UiElementCatalog(
            ui_backend
        ),
    )

    result = tool.execute(
        {
            "window": "Save As",
        }
    )

    assert result == [
        {
            "name": "Save",
            "control_type": "Button",
            "enabled": True,
        }
    ]


def test_list_ui_elements_merges_duplicate_title_windows(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=10,
                title="Calculator",
            ),
            WindowEntry(
                handle=20,
                title="Calculator",
            ),
        )
    )

    ui_backend = FakeUiBackend(
        {
            10: (
                UiElementEntry(
                    locator="display",
                    name="Display is 0",
                    control_type="Text",
                    enabled=True,
                ),
            ),
            20: (
                UiElementEntry(
                    locator="seven",
                    name="7",
                    control_type="Button",
                    enabled=True,
                ),
            ),
        }
    )

    tool = ListUiElementsTool(
        window_catalog=WindowCatalog(
            window_backend
        ),
        ui_catalog=UiElementCatalog(
            ui_backend
        ),
    )

    result = tool.execute(
        {
            "window": "Calculator",
        }
    )

    assert result == [
        {
            "name": "Display is 0",
            "control_type": "Text",
            "enabled": True,
        },
        {
            "name": "7",
            "control_type": "Button",
            "enabled": True,
        },
    ]


def test_list_ui_elements_deduplicates_duplicate_controls(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=10,
                title="Calculator",
            ),
            WindowEntry(
                handle=20,
                title="Calculator",
            ),
        )
    )

    repeated_button = UiElementEntry(
        locator="different-internal-locator",
        name="7",
        control_type="Button",
        enabled=True,
    )

    ui_backend = FakeUiBackend(
        {
            10: (
                UiElementEntry(
                    locator="one",
                    name="7",
                    control_type="Button",
                    enabled=True,
                ),
            ),
            20: (
                repeated_button,
            ),
        }
    )

    tool = ListUiElementsTool(
        window_catalog=WindowCatalog(
            window_backend
        ),
        ui_catalog=UiElementCatalog(
            ui_backend
        ),
    )

    result = tool.execute(
        {
            "window": "Calculator",
        }
    )

    assert result == [
        {
            "name": "7",
            "control_type": "Button",
            "enabled": True,
        }
    ]


def test_click_ui_element_resolves_single_window_target(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=77,
                title="Save As",
            ),
        )
    )

    ui_backend = FakeUiBackend(
        {
            77: (
                UiElementEntry(
                    locator="button-1",
                    name="Cancel",
                    control_type="Button",
                    enabled=True,
                ),
                UiElementEntry(
                    locator="button-2",
                    name="Save",
                    control_type="Button",
                    enabled=True,
                ),
            )
        }
    )

    tool = ClickUiElementTool(
        window_catalog=WindowCatalog(
            window_backend
        ),
        ui_catalog=UiElementCatalog(
            ui_backend
        ),
    )

    result = tool.execute(
        {
            "window": "Save As",
            "element": "Save",
            "control_type": "Button",
        }
    )

    assert window_backend.focused == [
        77,
    ]

    assert ui_backend.clicked == [
        (
            77,
            "button-2",
        )
    ]

    assert isinstance(
        result,
        dict,
    )

    assert result[
        "element"
    ] == "Save"


def test_click_ui_disambiguates_duplicate_window_using_control(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=100,
                title="Calculator",
            ),
            WindowEntry(
                handle=200,
                title="Calculator",
            ),
        )
    )

    ui_backend = FakeUiBackend(
        {
            100: (
                UiElementEntry(
                    locator="host-text",
                    name="Calculator",
                    control_type="Text",
                    enabled=True,
                ),
            ),
            200: (
                UiElementEntry(
                    locator="seven-button",
                    name="7",
                    control_type="Button",
                    enabled=True,
                ),
            ),
        }
    )

    tool = ClickUiElementTool(
        window_catalog=WindowCatalog(
            window_backend
        ),
        ui_catalog=UiElementCatalog(
            ui_backend
        ),
    )

    result = tool.execute(
        {
            "window": "Calculator",
            "element": "7",
            "control_type": "Button",
        }
    )

    assert window_backend.focused == [
        200,
    ]

    assert ui_backend.clicked == [
        (
            200,
            "seven-button",
        )
    ]

    assert isinstance(
        result,
        dict,
    )

    assert result[
        "element"
    ] == "7"


def test_click_ui_refuses_real_remaining_ambiguity(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=100,
                title="Calculator",
            ),
            WindowEntry(
                handle=200,
                title="Calculator",
            ),
        )
    )

    ui_backend = FakeUiBackend(
        {
            100: (
                UiElementEntry(
                    locator="seven-1",
                    name="7",
                    control_type="Button",
                    enabled=True,
                ),
            ),
            200: (
                UiElementEntry(
                    locator="seven-2",
                    name="7",
                    control_type="Button",
                    enabled=True,
                ),
            ),
        }
    )

    tool = ClickUiElementTool(
        window_catalog=WindowCatalog(
            window_backend
        ),
        ui_catalog=UiElementCatalog(
            ui_backend
        ),
    )

    with pytest.raises(
        ValueError,
        match="ambiguous",
    ):
        tool.execute(
            {
                "window": "Calculator",
                "element": "7",
                "control_type": "Button",
            }
        )

    assert window_backend.focused == []
    assert ui_backend.clicked == []


def test_ui_catalog_rejects_ambiguous_elements(
    tmp_path: Path,
) -> None:
    del tmp_path

    ui_backend = FakeUiBackend(
        {
            1: (
                UiElementEntry(
                    locator="1",
                    name="Open file",
                    control_type="Button",
                    enabled=True,
                ),
                UiElementEntry(
                    locator="2",
                    name="Open folder",
                    control_type="Button",
                    enabled=True,
                ),
            )
        }
    )

    catalog = UiElementCatalog(
        ui_backend
    )

    with pytest.raises(
        ValueError,
        match="ambiguous",
    ):
        catalog.resolve(
            window_handle=1,
            requested_name="Open",
        )


def test_ui_tools_refuse_to_automate_jarvis_itself(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=999,
                title="JARVIS",
            ),
        )
    )

    ui_backend = FakeUiBackend(
        {
            999: (
                UiElementEntry(
                    locator="1",
                    name="Always allow",
                    control_type="Button",
                    enabled=True,
                ),
            )
        }
    )

    tool = ClickUiElementTool(
        window_catalog=WindowCatalog(
            window_backend
        ),
        ui_catalog=UiElementCatalog(
            ui_backend
        ),
    )

    with pytest.raises(
        ValueError,
        match="cannot automate its own",
    ):
        tool.execute(
            {
                "window": "JARVIS",
                "element": "Always allow",
            }
        )

    assert ui_backend.clicked == []