from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ModelRequest(BaseModel):
    prompt: str = Field(min_length=1)
    system_prompt: str | None = None


class ModelResponse(BaseModel):
    text: str
    provider: str
    model: str


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a model response."""
        raise NotImplementedError