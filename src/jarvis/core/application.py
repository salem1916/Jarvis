from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import ModelProvider, ModelRequest, ModelResponse
from jarvis.tools.service import ToolService


class JarvisApplication:
    def __init__(
        self,
        tool_service: ToolService,
        model_provider: ModelProvider,
    ) -> None:
        self.tool_service = tool_service
        self.model_provider = model_provider

    def execute_tool(self, request: ToolRequest) -> object:
        return self.tool_service.execute(request)

    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        request = ModelRequest(
            prompt=prompt,
            system_prompt=system_prompt,
        )

        return self.model_provider.generate(request)