from jarvis.core.application import JarvisApplication
from jarvis.core.config import JarvisSettings
from jarvis.models.base import ModelProvider
from jarvis.models.ollama import OllamaProvider
from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.security.filesystem_scope_store import FilesystemScopeStore
from jarvis.security.permission_mode import PermissionMode
from jarvis.security.permission_mode_store import PermissionModeStore
from jarvis.security.policy import (
    PermissionDecision,
    PermissionPolicy,
)
from jarvis.tools.application_catalog import ApplicationCatalog
from jarvis.tools.calculator import CalculatorTool
from jarvis.tools.click_ui_element import ClickUiElementTool
from jarvis.tools.close_window import (
    CloseWindowTool,
    Win32CloseWindowBackend,
)
from jarvis.tools.control_window import ControlWindowTool
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.keyboard_action import (
    KeyboardActionTool,
    Win32KeyboardActionBackend,
)
from jarvis.tools.list_applications import ListApplicationsTool
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.list_filesystem_scopes import ListFilesystemScopesTool
from jarvis.tools.list_open_windows import ListOpenWindowsTool
from jarvis.tools.list_ui_elements import ListUiElementsTool
from jarvis.tools.open_application import OpenApplicationTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService
from jarvis.tools.system_info import SystemInfoTool
from jarvis.tools.trash_file import TrashFileTool
from jarvis.tools.type_text import (
    TypeTextTool,
    Win32TextInputBackend,
)
from jarvis.tools.ui_automation import (
    PywinautoUiAutomationBackend,
    UiElementCatalog,
)
from jarvis.tools.window_catalog import (
    Win32WindowBackend,
    WindowCatalog,
)
from jarvis.tools.write_file import WriteFileTool


def build_model_provider(
    settings: JarvisSettings,
) -> ModelProvider:
    """
    Build the configured AI model backend.
    """

    if settings.model_provider == "ollama":
        return OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )

    raise ValueError(
        "Unsupported model provider: "
        f"{settings.model_provider}"
    )


def build_application(
    settings: JarvisSettings,
) -> JarvisApplication:
    """
    Assemble the complete JARVIS runtime.
    """

    # =================================================
    # AUTOMATIC CAPABILITIES
    # =================================================

    allowed_capabilities: set[Capability] = {
        Capability.CALCULATE,
    }

    if settings.allow_read_file:
        allowed_capabilities.add(
            Capability.READ_FILE
        )

    if settings.allow_system_info:
        allowed_capabilities.add(
            Capability.READ_SYSTEM_INFO
        )

    # =================================================
    # USER-CONFIGURABLE SIDE-EFFECT CAPABILITIES
    # =================================================

    default_modes: dict[
        Capability,
        PermissionMode,
    ] = {
        Capability.WRITE_FILE:
            PermissionMode.ASK,

        Capability.DELETE_FILE:
            PermissionMode.ASK,

        Capability.OPEN_APPLICATION:
            PermissionMode.ASK,

        Capability.CONTROL_APPLICATION:
            PermissionMode.ASK,

        Capability.CLOSE_APPLICATION:
            PermissionMode.ASK,

        Capability.TYPE_TEXT:
            PermissionMode.ASK,

        Capability.KEYBOARD_ACTION:
            PermissionMode.ASK,

        Capability.INSPECT_UI:
            PermissionMode.ASK,

        Capability.CLICK_UI:
            PermissionMode.ASK,
    }

    # =================================================
    # PERSISTED PERMISSION MODES
    # =================================================

    permission_mode_store: PermissionModeStore | None = None

    persisted_modes: dict[
        Capability,
        PermissionMode,
    ] = {}

    if settings.persist_permission_modes:
        permission_mode_store = PermissionModeStore(
            settings.state_dir
            / "permission_modes.json"
        )

        persisted_modes = permission_mode_store.load()

    permission_modes: dict[
        Capability,
        PermissionMode,
    ] = {
        **default_modes,
        **{
            capability: mode
            for capability, mode
            in persisted_modes.items()
            if capability in default_modes
        },
    }

    confirmation_capabilities: set[
        Capability
    ] = set()

    for capability, mode in permission_modes.items():
        decision = mode.to_decision()

        if decision is PermissionDecision.ALLOW:
            allowed_capabilities.add(
                capability
            )

        elif (
            decision
            is PermissionDecision.REQUIRE_CONFIRMATION
        ):
            confirmation_capabilities.add(
                capability
            )

    permission_policy = PermissionPolicy(
        allowed=allowed_capabilities,
        require_confirmation=confirmation_capabilities,
    )

    # =================================================
    # FILESYSTEM SCOPES
    # =================================================

    filesystem_scope_store: FilesystemScopeStore | None = None

    persisted_roots = ()

    if settings.persist_filesystem_scopes:
        filesystem_scope_store = FilesystemScopeStore(
            settings.state_dir
            / "filesystem_scopes.json"
        )

        persisted_roots = filesystem_scope_store.load()

    filesystem_scope_policy = FilesystemScopePolicy(
        settings.workspace_dir,
        allowed_roots=persisted_roots,
    )

    # =================================================
    # TRUSTED APPLICATION / WINDOW / UI DISCOVERY
    # =================================================

    application_catalog = ApplicationCatalog()

    window_backend = Win32WindowBackend()

    window_catalog = WindowCatalog(
        window_backend
    )

    close_window_backend = Win32CloseWindowBackend()

    text_input_backend = Win32TextInputBackend()

    keyboard_action_backend = Win32KeyboardActionBackend()

    ui_automation_backend = PywinautoUiAutomationBackend()

    ui_element_catalog = UiElementCatalog(
        ui_automation_backend
    )

    # =================================================
    # TOOL REGISTRY
    # =================================================

    registry = ToolRegistry()

    # Filesystem
    registry.register(
        ListFilesystemScopesTool(
            filesystem_scope_policy
        )
    )

    registry.register(
        ReadFileTool(
            settings.workspace_dir,
            scope_policy=filesystem_scope_policy,
        )
    )

    registry.register(
        ListDirectoryTool(
            settings.workspace_dir,
            scope_policy=filesystem_scope_policy,
        )
    )

    registry.register(
        WriteFileTool(
            settings.workspace_dir,
            scope_policy=filesystem_scope_policy,
        )
    )

    registry.register(
        TrashFileTool(
            settings.workspace_dir,
            scope_policy=filesystem_scope_policy,
        )
    )

    # Applications
    registry.register(
        ListApplicationsTool(
            application_catalog
        )
    )

    registry.register(
        OpenApplicationTool(
            application_catalog
        )
    )

    # Windows
    registry.register(
        ListOpenWindowsTool(
            window_catalog
        )
    )

    registry.register(
        ControlWindowTool(
            window_catalog
        )
    )

    registry.register(
        CloseWindowTool(
            catalog=window_catalog,
            backend=close_window_backend,
        )
    )

    # Input
    registry.register(
        TypeTextTool(
            catalog=window_catalog,
            text_backend=text_input_backend,
        )
    )

    registry.register(
        KeyboardActionTool(
            catalog=window_catalog,
            keyboard_backend=keyboard_action_backend,
        )
    )

    # UI Automation
    registry.register(
        ListUiElementsTool(
            window_catalog=window_catalog,
            ui_catalog=ui_element_catalog,
        )
    )

    registry.register(
        ClickUiElementTool(
            window_catalog=window_catalog,
            ui_catalog=ui_element_catalog,
        )
    )

    # Utilities
    registry.register(
        SystemInfoTool()
    )

    registry.register(
        CalculatorTool()
    )

    # =================================================
    # SECURE EXECUTION
    # =================================================

    executor = ToolExecutor(
        permission_policy
    )

    tool_service = ToolService(
        registry,
        executor,
    )

    model_provider = build_model_provider(
        settings
    )

    return JarvisApplication(
        tool_service=tool_service,
        model_provider=model_provider,
        filesystem_scope_policy=filesystem_scope_policy,
        filesystem_scope_store=filesystem_scope_store,
        permission_mode_store=permission_mode_store,
        permission_modes=permission_modes,
    )