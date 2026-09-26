from jarvis.core.application import JarvisApplication
from jarvis.core.config import JarvisSettings
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.list_directory import ListDirectoryTool
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


def build_application(settings: JarvisSettings) -> JarvisApplication:
    allowed_capabilities: set[Capability] = set()

    if settings.allow_read_file:
        allowed_capabilities.add(Capability.READ_FILE)

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

    executor = ToolExecutor(policy)
    tool_service = ToolService(registry, executor)

    return JarvisApplication(tool_service)