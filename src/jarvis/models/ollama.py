import httpx

from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)


class OllamaProvider(ModelProvider):
    """
    Model provider for a local Ollama server.

    JARVIS talks to Ollama through its HTTP API.

    This provider is responsible for:
    - sending prompts to Ollama
    - sending available tool definitions
    - receiving normal text responses
    - receiving structured tool-call requests

    IMPORTANT:
    This class does NOT execute tools.

    It only tells the rest of JARVIS:
    "The model wants to call this tool with these arguments."
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
        Send a ModelRequest to Ollama and convert the result
        into JARVIS's provider-independent ModelResponse.
        """

        # Ollama expects conversation messages.
        messages: list[dict[str, str]] = []

        # Add the JARVIS system prompt first when one exists.
        if request.system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": request.system_prompt,
                }
            )

        # Add the user's message.
        messages.append(
            {
                "role": "user",
                "content": request.prompt,
            }
        )

        # Base Ollama request.
        #
        # think=False:
        # prevents the model from doing long visible reasoning
        # for simple JARVIS requests.
        #
        # keep_alive="10m":
        # keeps the model loaded for faster follow-up requests.
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": "10m",
        }

        # If JARVIS gives the model tools, convert our generic
        # ModelToolDefinition objects into Ollama's tool format.
        #
        # Example:
        #
        # JARVIS:
        # ModelToolDefinition(
        #     name="list_directory",
        #     ...
        # )
        #
        # becomes:
        #
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "list_directory",
        #         ...
        #     }
        # }
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

        # Send the request to the local Ollama server.
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

        # Convert Ollama's JSON response into Python data.
        data = response.json()

        message = data.get("message")

        if not isinstance(message, dict):
            raise TypeError(
                "Ollama returned an invalid response."
            )

        # Tool-call responses can legitimately have an empty
        # content field, so "" is allowed here.
        content = message.get(
            "content",
            "",
        )

        if not isinstance(content, str):
            raise TypeError(
                "Ollama response did not contain valid text."
            )

        # This will hold any tool requests made by the model.
        #
        # Again: we are NOT executing anything here.
        tool_calls: list[ModelToolCall] = []

        raw_tool_calls = message.get(
            "tool_calls",
            [],
        )

        if not isinstance(raw_tool_calls, list):
            raise TypeError(
                "Ollama returned invalid tool calls."
            )

        # Convert Ollama-specific tool calls into our own
        # provider-independent ModelToolCall format.
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

        # Return a generic JARVIS response.
        #
        # Other providers such as OpenAI or Claude will later
        # return this same ModelResponse type.
        return ModelResponse(
            text=content,
            provider=self.name,
            model=self.model,
            tool_calls=tool_calls,
        )