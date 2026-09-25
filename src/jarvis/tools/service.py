from jarvis.core.tool_request import ToolRequest
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.registry import ToolRegistry


class ToolService:
    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor,
    ) -> None:
        self.registry = registry
        self.executor = executor

    def execute(self, request: ToolRequest) -> object:
        tool = self.registry.get(request.tool_name)

        return self.executor.execute(
            tool,
            request.arguments,
        )
    