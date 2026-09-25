from pydantic import BaseModel, Field


class ToolRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)