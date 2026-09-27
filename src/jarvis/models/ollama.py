import httpx

from jarvis.models.base import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)


class OllamaProvider(ModelProvider):
    """
    Local model provider using Ollama's HTTP API.

    Responsibilities:

    - send normal conversations
    - send tool definitions
    - preserve multi-turn message history
    - send REAL tool results back using role="tool"
    - parse model tool requests

    IMPORTANT:
    This provider NEVER executes tools.
    """

    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """
        Send one request to Ollama.

        If ModelRequest.messages contains conversation history,
        that history is used.

        Otherwise we preserve the old simple behavior using
        system_prompt + prompt.
        """

        messages = self._build_messages(
            request
        )

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "stream": False,

            # Keep normal JARVIS interaction fast.
            "think": False,

            # Avoid reloading the model for every request.
            "keep_alive": "10m",
        }

        # Convert JARVIS's generic tool definitions into
        # Ollama's function-calling format.
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in request.tools
            ]

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )

            response.raise_for_status()

        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Could not communicate with the Ollama server."
            ) from exc

        data = response.json()

        message = data.get(
            "message"
        )

        if not isinstance(
            message,
            dict,
        ):
            raise TypeError(
                "Ollama returned an invalid response."
            )

        content = message.get(
            "content",
            "",
        )

        if not isinstance(
            content,
            str,
        ):
            raise TypeError(
                "Ollama response did not contain valid text."
            )

        tool_calls: list[ModelToolCall] = []

        raw_tool_calls = message.get(
            "tool_calls",
            [],
        )

        if not isinstance(
            raw_tool_calls,
            list,
        ):
            raise TypeError(
                "Ollama returned invalid tool calls."
            )

        for raw_tool_call in raw_tool_calls:
            if not isinstance(
                raw_tool_call,
                dict,
            ):
                raise TypeError(
                    "Ollama returned an invalid tool call."
                )

            function = raw_tool_call.get(
                "function"
            )

            if not isinstance(
                function,
                dict,
            ):
                raise TypeError(
                    "Ollama tool call has no valid function."
                )

            name = function.get(
                "name"
            )

            arguments = function.get(
                "arguments",
                {},
            )

            if not isinstance(
                name,
                str,
            ):
                raise TypeError(
                    "Ollama tool call has no valid name."
                )

            if not isinstance(
                arguments,
                dict,
            ):
                raise TypeError(
                    "Ollama tool call has invalid arguments."
                )

            tool_calls.append(
                ModelToolCall(
                    name=name,
                    arguments=arguments,
                )
            )

        return ModelResponse(
            text=content,
            provider=self.name,
            model=self.model,
            tool_calls=tool_calls,
        )

    def _build_messages(
        self,
        request: ModelRequest,
    ) -> list[dict[str, object]]:
        """
        Convert JARVIS ModelMessage objects into Ollama messages.

        Native tool history looks like:

        user
          ↓
        assistant + tool_calls
          ↓
        tool result
          ↓
        assistant continues

        This is much better than rewriting tool results into
        another fake user prompt.
        """

        # If real conversation history exists, use it.
        if request.messages:
            return [
                self._convert_message(
                    message
                )
                for message in request.messages
            ]

        # Backwards-compatible simple request.
        messages: list[dict[str, object]] = []

        if request.system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": request.system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": request.prompt,
            }
        )

        return messages

    @staticmethod
    def _convert_message(
        message: ModelMessage,
    ) -> dict[str, object]:
        """
        Convert one generic JARVIS message into the
        structure expected by Ollama.
        """

        converted: dict[str, object] = {
            "role": message.role,
            "content": message.content,
        }

        # Assistant messages may contain requests
        # for one or more tools.
        if message.tool_calls:
            converted["tool_calls"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]

        # Ollama requires the tool name on a tool-result
        # message so it knows which call produced the result.
        if message.role == "tool":
            if not message.tool_name:
                raise TypeError(
                    "Tool messages require a tool_name."
                )

            converted["tool_name"] = (
                message.tool_name
            )

        return converted