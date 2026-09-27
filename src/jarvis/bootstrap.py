from jarvis.core.application import JarvisApplication
from jarvis.core.config import JarvisSettings
from jarvis.models.base import ModelProvider
from jarvis.models.ollama import OllamaProvider
from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.calculator import CalculatorTool
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.list_filesystem_scopes import ListFilesystemScopesTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService
from jarvis.tools.system_info import SystemInfoTool


def build_model_provider(
    settings: JarvisSettings,
) -> ModelProvider:
    """
    Build the configured AI model backend.

    The rest of JARVIS communicates through ModelProvider
    rather than depending directly on Ollama.
    """

    if settings.model_provider == "ollama":
        return OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )

    raise ValueError(
        f"Unsupported model provider: "
        f"{settings.model_provider}"
    )


def build_application(
    settings: JarvisSettings,
) -> JarvisApplication:
    """
    Assemble the complete JARVIS application.

    Security uses two separate concepts:

        Capability
            What kind of operation may happen?

        FilesystemScopePolicy
            Where may that operation happen?

    READ_FILE therefore does not automatically mean
    unrestricted access to the computer.
    """

    # -------------------------------------------------
    # Capability permissions
    # -------------------------------------------------

    allowed_capabilities: set[Capability] = {
        # Safe deterministic local computation.
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

    permission_policy = PermissionPolicy(
        allowed=allowed_capabilities,
    )

    # -------------------------------------------------
    # Filesystem resource scopes
    #
    # Workspace is always available.
    #
    # Additional user-approved folders can later be
    # added through the desktop Permissions page.
    # -------------------------------------------------

    filesystem_scope_policy = FilesystemScopePolicy(
        settings.workspace_dir
    )

    # -------------------------------------------------
    # Tool registry
    # -------------------------------------------------

    registry = ToolRegistry()

    # The model can discover which real folders have
    # already been approved.
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
        SystemInfoTool()
    )

    registry.register(
        CalculatorTool()
    )

    # -------------------------------------------------
    # Secure tool execution
    # -------------------------------------------------

    executor = ToolExecutor(
        permission_policy
    )

    tool_service = ToolService(
        registry,
        executor,
    )

    # -------------------------------------------------
    # AI backend
    # -------------------------------------------------

    model_provider = build_model_provider(
        settings
    )

    # -------------------------------------------------
    # Application facade
    # -------------------------------------------------

    return JarvisApplication(
        tool_service=tool_service,
        model_provider=model_provider,
        filesystem_scope_policy=filesystem_scope_policy,
    )