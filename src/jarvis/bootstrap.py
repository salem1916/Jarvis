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
from jarvis.tools.calculator import CalculatorTool
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.list_filesystem_scopes import ListFilesystemScopesTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService
from jarvis.tools.system_info import SystemInfoTool
from jarvis.tools.trash_file import TrashFileTool
from jarvis.tools.write_file import WriteFileTool


def build_model_provider(
    settings: JarvisSettings,
) -> ModelProvider:
    """
    Build the configured AI model backend.

    The rest of JARVIS communicates through ModelProvider,
    so Ollama can later be replaced or joined by other
    providers without changing the entire application.
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

    This is the application's composition root.

    It connects:

        configuration
            ↓
        permission modes
            ↓
        PermissionPolicy
            ↓
        filesystem scopes
            ↓
        tools
            ↓
        ToolExecutor / ToolService
            ↓
        AI model provider
            ↓
        JarvisApplication
    """

    # =================================================
    # BASE AUTOMATIC CAPABILITIES
    # =================================================
    #
    # These capabilities are automatically allowed
    # depending on JARVIS configuration.
    # =================================================

    allowed_capabilities: set[Capability] = {
        # Pure deterministic local calculation.
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
    #     WRITE_FILE  -> Ask every time
    #     DELETE_FILE -> Ask every time
    #
    # Later the user may choose:
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
    }

    # -------------------------------------------------
    # Optional persistent permission-mode storage.
    # -------------------------------------------------

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
    # Merge defaults with persisted user choices.
    #
    # Only capabilities that JARVIS currently exposes as
    # configurable are accepted here.
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

    # Capabilities that currently require explicit
    # human confirmation.
    confirmation_capabilities: set[
        Capability
    ] = set()

    # -------------------------------------------------
    # Convert human-facing PermissionMode values into
    # low-level PermissionPolicy decisions.
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

        # PermissionDecision.DENY requires no set membership.
        #
        # PermissionPolicy defaults to DENY when a capability
        # is in neither allowed_capabilities nor
        # confirmation_capabilities.

    # =================================================
    # CAPABILITY SECURITY POLICY
    # =================================================

    permission_policy = PermissionPolicy(
        allowed=allowed_capabilities,
        require_confirmation=confirmation_capabilities,
    )

    # =================================================
    # FILESYSTEM SCOPES
    # =================================================
    #
    # Capability answers:
    #
    #     "May JARVIS read/write/delete?"
    #
    # FilesystemScopePolicy answers:
    #
    #     "WHERE may JARVIS operate?"
    #
    # Both layers are required.
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
    # Read-only filesystem tools
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
    # Side-effect filesystem tools
    #
    # WRITE_FILE and DELETE_FILE are protected by the
    # PermissionPolicy configured above.
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
    # Other tools
    # -------------------------------------------------

    registry.register(
        SystemInfoTool()
    )

    registry.register(
        CalculatorTool()
    )

    # =================================================
    # SECURE TOOL EXECUTION
    # =================================================

    executor = ToolExecutor(
        permission_policy
    )

    tool_service = ToolService(
        registry,
        executor,
    )

    # =================================================
    # AI MODEL BACKEND
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