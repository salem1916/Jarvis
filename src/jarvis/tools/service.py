from jarvis.core.tool_request import ToolRequest
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.registry import ToolRegistry


class ToolService:
    """
    Trusted gateway between JARVIS orchestration and tools.

    Responsibilities:

        ToolRequest
            ↓
        ToolRegistry
            ↓
        ToolExecutor
            ↓
        PermissionPolicy
            ↓
        Tool

    The model never interacts with ToolExecutor directly.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor,
    ) -> None:
        self.registry = registry
        self.executor = executor

    def execute(
        self,
        request: ToolRequest,
        *,
        confirmed: bool = False,
    ) -> object:
        """
        Execute one structured tool request.

        `confirmed=True` is used only by trusted JARVIS
        orchestration after explicit human approval.

        It does not bypass a DENY decision.
        """

        tool = self.registry.get(
            request.tool_name
        )

        return self.executor.execute(
            tool,
            request.arguments,
            confirmed=confirmed,
        )