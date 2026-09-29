import json

import httpx

from jarvis.models.base import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)


class OpenAICompatibleProvider(ModelProvider):
    """
    Generic provider for OpenAI-compatible Chat Completions APIs.

    Examples include providers such as Groq.

    Responsibilities:

    - send model conversations
    - translate JARVIS tool schemas
    - preserve assistant tool-call IDs
    - return real tool results to the correct tool call
    - parse structured model tool requests

    IMPORTANT:

    This provider NEVER executes tools.

    Tool execution remains inside the trusted JARVIS core.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        base_url: str,
        api_key: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        provider_name = provider_name.strip()
        model = model.strip()
        api_key = api_key.strip()

        if not provider_name:
            raise ValueError(
                "provider_name cannot be empty."
            )

        if not model:
            raise ValueError(
                "model cannot be empty."
            )

        if not api_key:
            raise ValueError(
                "api_key cannot be empty."
            )

        self.name = provider_name

        self.model = model

        self.base_url = base_url.rstrip(
            "/"
        )

        self.api_key = api_key

        self.timeout = timeout
        self.transport = transport

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """
        Generate one model response through an
        OpenAI-compatible Chat Completions endpoint.
        """

        payload: dict[
            str,
            object,
        ] = {
            "model": self.model,
            "messages": self._build_messages(
                request
            ),
            "stream": False,
        }

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

        headers = {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.post(
                    (
                        f"{self.base_url}"
                        "/chat/completions"
                    ),
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Could not communicate with "
                f"{self.name}."
            ) from exc

        except ValueError as exc:
            raise RuntimeError(
                f"{self.name} returned invalid JSON."
            ) from exc

        return self._parse_response(
            data
        )

    def _parse_response(
        self,
        data: object,
    ) -> ModelResponse:
        """
        Convert an OpenAI-compatible response into the
        provider-independent JARVIS response format.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "Model provider returned an invalid response."
            )

        choices = data.get(
            "choices"
        )

        if (
            not isinstance(
                choices,
                list,
            )
            or not choices
        ):
            raise TypeError(
                "Model provider returned no valid choices."
            )

        first_choice = choices[
            0
        ]

        if not isinstance(
            first_choice,
            dict,
        ):
            raise TypeError(
                "Model provider returned an invalid choice."
            )

        message = first_choice.get(
            "message"
        )

        if not isinstance(
            message,
            dict,
        ):
            raise TypeError(
                "Model provider returned an invalid message."
            )

        raw_content = message.get(
            "content"
        )

        if raw_content is None:
            content = ""

        elif isinstance(
            raw_content,
            str,
        ):
            content = raw_content

        else:
            raise TypeError(
                "Model provider returned invalid text."
            )

        raw_tool_calls = message.get(
            "tool_calls",
            [],
        )

        if raw_tool_calls is None:
            raw_tool_calls = []

        if not isinstance(
            raw_tool_calls,
            list,
        ):
            raise TypeError(
                "Model provider returned invalid tool calls."
            )

        tool_calls: list[
            ModelToolCall
        ] = []

        for raw_tool_call in raw_tool_calls:
            tool_calls.append(
                self._parse_tool_call(
                    raw_tool_call
                )
            )

        return ModelResponse(
            text=content,
            provider=self.name,
            model=self.model,
            tool_calls=tool_calls,
        )

    @staticmethod
    def _parse_tool_call(
        raw_tool_call: object,
    ) -> ModelToolCall:
        """
        Parse one OpenAI-compatible function call.
        """

        if not isinstance(
            raw_tool_call,
            dict,
        ):
            raise TypeError(
                "Model provider returned an invalid tool call."
            )

        call_id = raw_tool_call.get(
            "id"
        )

        if (
            not isinstance(
                call_id,
                str,
            )
            or not call_id
        ):
            raise TypeError(
                "Model tool call has no valid call ID."
            )

        function = raw_tool_call.get(
            "function"
        )

        if not isinstance(
            function,
            dict,
        ):
            raise TypeError(
                "Model tool call has no valid function."
            )

        name = function.get(
            "name"
        )

        if (
            not isinstance(
                name,
                str,
            )
            or not name
        ):
            raise TypeError(
                "Model tool call has no valid name."
            )

        raw_arguments = function.get(
            "arguments",
            "{}",
        )

        if isinstance(
            raw_arguments,
            str,
        ):
            try:
                arguments = json.loads(
                    raw_arguments
                )

            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Model tool call contains invalid "
                    "JSON arguments."
                ) from exc

        elif isinstance(
            raw_arguments,
            dict,
        ):
            arguments = raw_arguments

        else:
            raise TypeError(
                "Model tool call has invalid arguments."
            )

        if not isinstance(
            arguments,
            dict,
        ):
            raise TypeError(
                "Model tool-call arguments must be "
                "a JSON object."
            )

        return ModelToolCall(
            call_id=call_id,
            name=name,
            arguments=arguments,
        )

    def _build_messages(
        self,
        request: ModelRequest,
    ) -> list[
        dict[
            str,
            object,
        ]
    ]:
        """
        Convert provider-independent JARVIS messages into
        OpenAI-compatible messages.
        """

        if request.messages:
            return [
                self._convert_message(
                    message
                )
                for message in request.messages
            ]

        messages: list[
            dict[
                str,
                object,
            ]
        ] = []

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
    ) -> dict[
        str,
        object,
    ]:
        """
        Convert one generic JARVIS message.

        OpenAI-compatible APIs require IDs to associate
        assistant tool requests with subsequent tool results.
        """

        if message.role == "tool":
            if not message.tool_call_id:
                raise TypeError(
                    "OpenAI-compatible tool-result messages "
                    "require tool_call_id."
                )

            return {
                "role": "tool",
                "tool_call_id": (
                    message.tool_call_id
                ),
                "content": message.content,
            }

        converted: dict[
            str,
            object,
        ] = {
            "role": message.role,
            "content": message.content,
        }

        if message.tool_calls:
            converted_tool_calls: list[
                dict[
                    str,
                    object,
                ]
            ] = []

            for tool_call in (
                message.tool_calls
            ):
                if not tool_call.call_id:
                    raise TypeError(
                        "OpenAI-compatible assistant tool "
                        "calls require call_id."
                    )

                converted_tool_calls.append(
                    {
                        "id": tool_call.call_id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(
                                tool_call.arguments,
                                ensure_ascii=False,
                            ),
                        },
                    }
                )

            converted[
                "tool_calls"
            ] = converted_tool_calls

        return converted