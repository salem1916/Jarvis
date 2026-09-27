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
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService
from jarvis.tools.system_info import SystemInfoTool


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
        f"Unsupported model provider: "
        f"{settings.model_provider}"
    )


def build_application(
    settings: JarvisSettings,
) -> JarvisApplication:
    """
    Assemble the JARVIS application.

    The filesystem scope policy is shared by all filesystem
    tools so changing an approved root immediately affects
    every filesystem operation.
    """

    # -------------------------------------------------
    # Capability permissions
    # -------------------------------------------------

    allowed_capabilities: set[Capability] = {
        # Pure deterministic local computation.
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
    # Initially ONLY the workspace is included.
    #
    # Later the user may add:
    #
    # Documents
    # Downloads
    # Desktop
    # custom folders
    # -------------------------------------------------

    filesystem_scope_policy = FilesystemScopePolicy(
        settings.workspace_dir
    )

    # -------------------------------------------------
    # Tool registry
    # -------------------------------------------------

    registry = ToolRegistry()

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
    # Secure execution layer
    # -------------------------------------------------

    executor = ToolExecutor(
        permission_policy
    )

    tool_service = ToolService(
        registry,
        executor,
    )

    # -------------------------------------------------
    # Model backend
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