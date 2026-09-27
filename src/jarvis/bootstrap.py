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
from jarvis.tools.control_window import ControlWindowTool
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.list_applications import ListApplicationsTool
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.list_filesystem_scopes import ListFilesystemScopesTool
from jarvis.tools.list_open_windows import ListOpenWindowsTool
from jarvis.tools.open_application import OpenApplicationTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService
from jarvis.tools.system_info import SystemInfoTool
from jarvis.tools.trash_file import TrashFileTool
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

    JARVIS talks to the abstract ModelProvider interface,
    allowing Ollama or other providers to be swapped later.
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

    This is JARVIS's composition root.

    It connects:

        configuration
            ↓
        permissions
            ↓
        filesystem/application/window policies
            ↓
        tools
            ↓
        secure tool execution
            ↓
        AI model
            ↓
        JarvisApplication
    """

    # =================================================
    # AUTOMATIC CAPABILITIES
    # =================================================
    #
    # These may execute without confirmation when enabled
    # in JARVIS configuration.
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
    # USER-CONFIGURABLE SIDE-EFFECT PERMISSIONS
    # =================================================
    #
    # Safe defaults:
    #
    # WRITE_FILE
    #     Ask before modifying files.
    #
    # DELETE_FILE
    #     Ask before moving files to Recycle Bin.
    #
    # OPEN_APPLICATION
    #     Ask before launching applications.
    #
    # CONTROL_APPLICATION
    #     Ask before changing window state.
    #
    # The Permissions UI may later change these to:
    #
    #     DENY
    #     ASK
    #     ALLOW_SESSION
    #     ALWAYS_ALLOW
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

    # -------------------------------------------------
    # Start with safe defaults, then apply persisted
    # choices for capabilities JARVIS currently supports.
    # -------------------------------------------------

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

    # -------------------------------------------------
    # Convert human-facing PermissionMode values into the
    # lower-level PermissionPolicy representation.
    # -------------------------------------------------

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

        # DENY requires no membership in either set.
        #
        # PermissionPolicy defaults to DENY.

    # =================================================
    # SECURITY POLICY
    # =================================================

    permission_policy = PermissionPolicy(
        allowed=allowed_capabilities,
        require_confirmation=confirmation_capabilities,
    )

    # =================================================
    # FILESYSTEM SCOPES
    # =================================================
    #
    # Capability security determines:
    #
    #     WHAT JARVIS may do.
    #
    # FilesystemScopePolicy determines:
    #
    #     WHERE JARVIS may do it.
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
    # TRUSTED WINDOWS APPLICATION CATALOG
    # =================================================
    #
    # This discovers applications from trusted Windows
    # locations such as the Start Menu.
    #
    # The model never supplies executable paths.
    # =================================================

    application_catalog = ApplicationCatalog()

    # =================================================
    # TRUSTED WINDOWS WINDOW CATALOG
    # =================================================
    #
    # Win32WindowBackend talks to the Windows APIs.
    #
    # WindowCatalog resolves human-friendly names such as:
    #
    #     "Discord"
    #     "Visual Studio Code"
    #     "Chrome"
    #
    # into actual window handles discovered by trusted code.
    #
    # The AI never supplies native window handles.
    # =================================================

    window_backend = Win32WindowBackend()

    window_catalog = WindowCatalog(
        window_backend
    )

    # =================================================
    # TOOL REGISTRY
    # =================================================

    registry = ToolRegistry()

    # -------------------------------------------------
    # Filesystem discovery
    # -------------------------------------------------

    registry.register(
        ListFilesystemScopesTool(
            filesystem_scope_policy
        )
    )

    # -------------------------------------------------
    # Filesystem read operations
    # -------------------------------------------------

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

    # -------------------------------------------------
    # Filesystem side effects
    # -------------------------------------------------

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

    # -------------------------------------------------
    # Installed application discovery
    # -------------------------------------------------

    registry.register(
        ListApplicationsTool(
            application_catalog
        )
    )

    # -------------------------------------------------
    # Application launching
    # -------------------------------------------------

    registry.register(
        OpenApplicationTool(
            application_catalog
        )
    )

    # -------------------------------------------------
    # Open-window discovery
    #
    # Read-only.
    # Requires READ_SYSTEM_INFO.
    # -------------------------------------------------

    registry.register(
        ListOpenWindowsTool(
            window_catalog
        )
    )

    # -------------------------------------------------
    # Window control
    #
    # First safe implementation supports only:
    #
    #     focus
    #     minimize
    #     maximize
    #     restore
    #
    # It deliberately does NOT support:
    #
    #     close
    #     kill
    #     click
    #     type
    #     execute commands
    # -------------------------------------------------

    registry.register(
        ControlWindowTool(
            window_catalog
        )
    )

    # -------------------------------------------------
    # System information
    # -------------------------------------------------

    registry.register(
        SystemInfoTool()
    )

    # -------------------------------------------------
    # Deterministic calculator
    # -------------------------------------------------

    registry.register(
        CalculatorTool()
    )

    # =================================================
    # SECURE TOOL EXECUTION
    # =================================================
    #
    # The model never calls tools directly.
    #
    # Model
    #   ↓
    # ToolRequest
    #   ↓
    # ToolService
    #   ↓
    # PermissionPolicy
    #   ↓
    # ToolExecutor
    #   ↓
    # Tool
    # =================================================

    executor = ToolExecutor(
        permission_policy
    )

    tool_service = ToolService(
        registry,
        executor,
    )

    # =================================================
    # AI MODEL
    # =================================================

    model_provider = build_model_provider(
        settings
    )

    # =================================================
    # FINAL APPLICATION
    # =================================================

    return JarvisApplication(
        tool_service=tool_service,
        model_provider=model_provider,
        filesystem_scope_policy=filesystem_scope_policy,
        filesystem_scope_store=filesystem_scope_store,
        permission_mode_store=permission_mode_store,
        permission_modes=permission_modes,
    )