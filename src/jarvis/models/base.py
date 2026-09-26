from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ModelToolDefinition(BaseModel):
    name: str = Field(min_length=1)
    description: str
    parameters: dict[str, object] = Field(default_factory=dict)


class ModelToolCall(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class ModelRequest(BaseModel):
    prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    tools: list[ModelToolDefinition] = Field(default_factory=list)


class ModelResponse(BaseModel):
    text: str
    provider: str
    model: str
    tool_calls: list[ModelToolCall] = Field(default_factory=list)


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """Generate a model response."""
        raise NotImplementedError