from jarvis.core.tool_request import ToolRequest
from jarvis.tools.service import ToolService


class JarvisApplication:
    def __init__(self, tool_service: ToolService) -> None:
        self.tool_service = tool_service

    def execute_tool(self, request: ToolRequest) -> object:
        return self.tool_service.execute(request)