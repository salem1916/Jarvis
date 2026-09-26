from jarvis.core.application import JarvisApplication
from jarvis.core.config import JarvisSettings
from jarvis.models.base import ModelProvider
from jarvis.models.ollama import OllamaProvider
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService
from jarvis.tools.system_info import SystemInfoTool


def build_model_provider(settings: JarvisSettings) -> ModelProvider:
    if settings.model_provider == "ollama":
        return OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )

    raise ValueError(
        f"Unsupported model provider: {settings.model_provider}"
    )


def build_application(settings: JarvisSettings) -> JarvisApplication:
    allowed_capabilities: set[Capability] = set()

    if settings.allow_read_file:
        allowed_capabilities.add(Capability.READ_FILE)

    if settings.allow_system_info:
        allowed_capabilities.add(Capability.READ_SYSTEM_INFO)

    policy = PermissionPolicy(
        allowed=allowed_capabilities,
    )

    registry = ToolRegistry()

    registry.register(
        ReadFileTool(settings.workspace_dir),
    )

    registry.register(
        ListDirectoryTool(settings.workspace_dir),
    )

    registry.register(
        SystemInfoTool(),
    )

    executor = ToolExecutor(policy)
    tool_service = ToolService(registry, executor)

    model_provider = build_model_provider(settings)

    return JarvisApplication(
        tool_service=tool_service,
        model_provider=model_provider,
    )