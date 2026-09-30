import re

from jarvis.tools.base import Tool
from jarvis.tools.registry import ToolRegistry


class ToolSelector:
    """
    Select the smallest useful set of JARVIS tools for a
    request.

    Purpose:

        Reduce model prompt size and therefore local-model
        latency.

    IMPORTANT:

        This is NOT a security layer.

        It only controls which registered tool definitions are
        shown to the model.

        Real execution still goes through:

            ToolService
                ↓
            PermissionPolicy
                ↓
            ToolExecutor

    If the selector is not confident about the request, it
    returns every registered tool so existing JARVIS behavior
    is preserved.
    """

    def __init__(
        self,
        registry: ToolRegistry,
    ) -> None:
        self.registry = registry

    def select(
        self,
        prompt: str,
    ) -> tuple[Tool, ...]:
        """
        Return tools relevant to one user request.

        Multiple intents are combined.

        Example:

            Open Calculator and click 7

        receives application-launch and UI-interaction tools,
        not the arithmetic calculator tool.
        """

        normalized = " ".join(
            prompt
            .strip()
            .casefold()
            .split()
        )

        if not normalized:
            return self.registry.tools()

        selected_names: set[str] = set()

        file_context = self._has_file_context(
            normalized
        )

        # =================================================
        # APPLICATION DISCOVERY
        # =================================================

        if re.search(
            (
                r"\b("
                r"list applications|"
                r"list apps|"
                r"available applications|"
                r"available apps|"
                r"installed applications|"
                r"installed apps"
                r")\b"
            ),
            normalized,
        ):
            selected_names.add(
                "list_applications"
            )

        # =================================================
        # APPLICATION LAUNCH
        # =================================================

        if (
            re.search(
                r"\b(open|launch|start)\b",
                normalized,
            )
            and not file_context
        ):
            selected_names.update(
                {
                    "list_applications",
                    "open_application",
                }
            )

        # =================================================
        # WINDOW DISCOVERY / CONTROL
        # =================================================

        if (
            "open windows" in normalized
            or "running windows" in normalized
        ):
            selected_names.add(
                "list_open_windows"
            )

        if (
            re.search(
                (
                    r"\b("
                    r"minimize|"
                    r"minimise|"
                    r"maximize|"
                    r"maximise|"
                    r"restore|"
                    r"focus"
                    r")\b"
                ),
                normalized,
            )
            or re.search(
                r"\bbring\b.*\bfront\b",
                normalized,
            )
        ):
            selected_names.update(
                {
                    "list_open_windows",
                    "control_window",
                }
            )

        if (
            re.search(
                r"\b(close|quit)\b",
                normalized,
            )
            and not file_context
        ):
            selected_names.update(
                {
                    "list_open_windows",
                    "close_window",
                }
            )

        # =================================================
        # UI INSPECTION / CLICKING
        # =================================================

        if (
            "ui elements" in normalized
            or "inspect ui" in normalized
            or "inspect the ui" in normalized
        ):
            selected_names.update(
                {
                    "list_open_windows",
                    "list_ui_elements",
                }
            )

        if (
            re.search(
                r"\bclick\b",
                normalized,
            )
            or re.search(
                r"\bpress\b.*\bbutton\b",
                normalized,
            )
        ):
            selected_names.update(
                {
                    "list_open_windows",
                    "list_ui_elements",
                    "click_ui_element",
                }
            )

        # =================================================
        # TEXT INPUT
        # =================================================

        if (
            re.search(
                r"\btype\b",
                normalized,
            )
            or re.search(
                r"\benter\s+(?:the\s+)?text\b",
                normalized,
            )
        ):
            selected_names.update(
                {
                    "list_open_windows",
                    "type_text",
                }
            )

        # =================================================
        # KEYBOARD ACTIONS
        # =================================================

        if (
            re.search(
                (
                    r"\b("
                    r"save|"
                    r"copy|"
                    r"paste|"
                    r"undo|"
                    r"redo"
                    r")\b"
                ),
                normalized,
            )
            or "select all" in normalized
            or re.search(
                r"\bpress\s+(enter|escape|tab)\b",
                normalized,
            )
        ):
            selected_names.update(
                {
                    "list_open_windows",
                    "keyboard_action",
                }
            )

        # =================================================
        # FILESYSTEM
        # =================================================

        if file_context:
            selected_names.add(
                "list_filesystem_scopes"
            )

            if re.search(
                (
                    r"\b("
                    r"list|"
                    r"browse|"
                    r"show|"
                    r"contents"
                    r")\b"
                ),
                normalized,
            ):
                selected_names.add(
                    "list_directory"
                )

            if re.search(
                r"\b(read|view|open)\b",
                normalized,
            ):
                selected_names.update(
                    {
                        "list_directory",
                        "read_file",
                    }
                )

            if re.search(
                r"\b(create|write|overwrite)\b",
                normalized,
            ):
                selected_names.update(
                    {
                        "list_directory",
                        "write_file",
                    }
                )

            if re.search(
                r"\b(delete|trash|remove)\b",
                normalized,
            ):
                selected_names.update(
                    {
                        "list_directory",
                        "trash_file",
                    }
                )

        # =================================================
        # SYSTEM INFORMATION
        # =================================================

        if re.search(
            (
                r"\b("
                r"system info|"
                r"system information|"
                r"cpu|"
                r"processor|"
                r"ram|"
                r"memory|"
                r"gpu"
                r")\b"
            ),
            normalized,
        ):
            selected_names.add(
                "system_info"
            )

        # =================================================
        # ARITHMETIC CALCULATOR
        # =================================================
        #
        # IMPORTANT:
        #
        # "Open Calculator" refers to the Windows application.
        #
        # Merely seeing the word "calculator" must therefore
        # NOT automatically expose the arithmetic calculator
        # tool.
        #
        # We select the arithmetic tool when the user actually
        # expresses a calculation intent.
        # =================================================

        if (
            re.search(
                r"\b(calculate|compute|arithmetic)\b",
                normalized,
            )
            or self._looks_like_math_request(
                normalized
            )
        ):
            selected_names.add(
                "calculator"
            )

        # =================================================
        # UNKNOWN / COMPLEX REQUEST
        # =================================================

        if not selected_names:
            return self.registry.tools()

        selected_tools = tuple(
            tool
            for tool in self.registry.tools()
            if tool.name in selected_names
        )

        # A partial/custom registry may not contain any of the
        # expected tools. Preserve existing behavior instead of
        # returning an empty tool set unexpectedly.
        if not selected_tools:
            return self.registry.tools()

        return selected_tools

    @staticmethod
    def _has_file_context(
        normalized: str,
    ) -> bool:
        """
        Determine whether words such as 'open' or 'delete'
        refer to filesystem content rather than applications.
        """

        if re.search(
            (
                r"\b("
                r"file|"
                r"files|"
                r"folder|"
                r"folders|"
                r"directory|"
                r"directories|"
                r"workspace|"
                r"path"
                r")\b"
            ),
            normalized,
        ):
            return True

        # Common filename/path hints.
        if re.search(
            r"\.[a-z0-9]{1,8}\b",
            normalized,
        ):
            return True

        if "\\" in normalized:
            return True

        return "/" in normalized

    @staticmethod
    def _looks_like_math_request(
        normalized: str,
    ) -> bool:
        """
        Detect obvious arithmetic requests without treating the
        Windows Calculator application name as arithmetic.

        Examples:

            12 + 5
            10 * 4
            100 / 8
            20% of 500
        """

        if re.search(
            r"\d\s*[\+\-\*/]\s*\d",
            normalized,
        ):
            return True

        return bool(
            re.search(
                r"\d+(?:\.\d+)?\s*%\s*(?:of\s+)?\d",
                normalized,
            )
        )