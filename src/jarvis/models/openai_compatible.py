import json
from collections.abc import Callable
from typing import Any

import httpx

from jarvis.core.request_control import RetryBudget, check_cancelled, current_control
from jarvis.models.base import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from jarvis.models.cancellable_http import provider_client
from jarvis.models.connection_errors import (
    ProviderConnectionError,
    ProviderCooldown,
    check_provider_response,
    network_failure,
)
from jarvis.models.retry import reserve_format_retry


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

    @property
    def supports_grounded_planner(self) -> bool:
        return self.name == "groq" and self.model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}

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
        self.usage_callback: Callable[[dict[str, Any], dict[str, str]], None] | None = None
        self.cooldown = ProviderCooldown()

    def _check_response(self, response: httpx.Response) -> None:
        try:
            check_provider_response(response, self.name)
        except ProviderConnectionError as error:
            self.cooldown.record(error)
            raise

    def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """
        Generate one model response through an
        OpenAI-compatible Chat Completions endpoint.
        """

        check_cancelled()
        self.cooldown.check(self.name)
        control = current_control()
        if request.json_schema is not None and (not self.supports_grounded_planner or request.tools):
            raise ValueError("This provider cannot run the grounded browser planner.")
        if control is not None and control.on_delta is not None and not request.tools and not request.json_output and request.json_schema is None:
            try:
                return self._generate_stream(request)
            except httpx.RequestError as exc:
                raise network_failure(self.name, exc) from exc
        check_cancelled()
        messages = self._build_messages(request)
        payload: dict[
            str,
            object,
        ] = {
            "model": self.model,
            "messages": messages,
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
            if request.tool_choice == "required":
                payload["tool_choice"] = "required"
                payload["parallel_tool_calls"] = False
                if self.name == "groq" and self.model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
                    payload["reasoning_effort"] = "low"
        if request.json_output and not request.tools and self.name in {"groq", "openai", "openrouter", "openrouter_free"}:
            payload["response_format"] = {"type": "json_object"}
        strict_envelope = request.json_output and request.json_schema is None and not request.tools and self.supports_grounded_planner
        if request.json_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "jarvis_browser_decision", "strict": True, "schema": request.json_schema,
            }}
            payload["reasoning_effort"] = "low"
        if strict_envelope:
            # GPT-OSS can emit a native tool channel despite JSON-object mode,
            # causing Groq's "Tool choice is none" rejection. Constrained
            # decoding keeps plans in the data channel. The inner object stays
            # flexible for research and registered tools with different schemas.
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "jarvis_controller_result", "strict": True, "schema": {
                    "type": "object", "properties": {"result_json": {"type": "string"}},
                    "required": ["result_json"], "additionalProperties": False,
                },
            }}
            messages.append({
                "role": "system", "content":
                'Your response is data for a trusted controller, not a native tool call. '
                'Place the complete JSON object requested above inside the result_json STRING '
                'of the required response envelope. Encode that inner object as a JSON string. '
                'Do not execute or invoke tools; the controller validates the returned data.',
            })

        headers = {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": "application/json",
        }

        try:
            with provider_client(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                budget = control.retry_budget if control else RetryBudget()
                while True:
                    response = client.post(self.base_url + "/chat/completions", headers=headers, json=payload)
                    native_controller = self.name == "groq" and request.tools and request.tool_choice == "required"
                    if (strict_envelope or native_controller) and response.status_code == 400:
                        try:
                            code = response.json().get("error", {}).get("code")
                        except (ValueError, AttributeError):
                            code = None
                        if code in {"tool_use_failed", "json_validate_failed", "output_parse_failed"} and reserve_format_retry(budget):
                            # Only regenerate this rejected proposal. Never use
                            # failed_generation as an executable tool request.
                            messages.append({"role": "system", "content":
                                ('The previous proposal violated the tool schema. Call exactly one attached '
                                 'function with arguments matching its schema. Preserve the full user goal.'
                                 if native_controller else
                                 'The previous proposal had an invalid response format. '
                                 'Return only {"result_json":"escaped JSON object with your next step"}. '
                                 'This is data, not a tool invocation. Preserve every part of the user goal.')})
                            continue
                    self._check_response(response)
                    data = response.json()
                    break

        except httpx.RequestError as exc:
            raise network_failure(self.name, exc) from exc

        except ProviderConnectionError:
            raise
        except ValueError as exc:
            raise RuntimeError(
                f"{self.name} returned invalid JSON."
            ) from exc

        if self.usage_callback:
            self.usage_callback(data.get("usage", {}), dict(response.headers))
        result = self._parse_response(data)
        if strict_envelope:
            try:
                inner = json.loads(result.text)["result_json"]
                if not isinstance(inner, str) or not isinstance(json.loads(inner), dict) or result.tool_calls:
                    raise ValueError("Invalid controller data")
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError("Groq returned an invalid controller result. No guessed action was performed.") from error
            result = result.model_copy(update={"text": inner})
        return result

    def _generate_stream(self, request: ModelRequest) -> ModelResponse:
        control = current_control()
        pieces: list[str] = []
        completed = False
        usage = {}
        with (
            provider_client(timeout=httpx.Timeout(self.timeout, connect=5), transport=self.transport) as client,
            client.stream("POST", self.base_url + "/chat/completions",
                               headers={"Authorization": "Bearer " + self.api_key},
                               json={"model": self.model, "messages": self._build_messages(request), "stream": True}) as response,
        ):
            self._check_response(response)
            for line in response.iter_lines():
                check_cancelled()
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    completed = True
                    break
                data = json.loads(raw)
                if data.get("error"):
                    raise ValueError(f"{self.name} could not complete this streamed reply.")
                if data.get("usage"):
                    usage = data["usage"]
                elif data.get("x_groq", {}).get("usage"):
                    usage = data["x_groq"]["usage"]
                choices = data.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]
                if choice.get("delta", {}).get("tool_calls"):
                    raise ValueError("A reasoning-only stream requested an unavailable action tool.")
                text = choice.get("delta", {}).get("content") or ""
                pieces.append(text)
                if control:
                    control.emit(text)
                if choice.get("finish_reason") == "stop":
                    completed = True
                elif choice.get("finish_reason") in {"length", "content_filter"}:
                    raise ValueError("The reply was cut short. Partial text is shown but was not saved as complete.")
        if not completed:
            raise ValueError(f"{self.name}'s stream ended before completion. Please retry.")
        if self.usage_callback:
            self.usage_callback(usage, dict(response.headers))
        return ModelResponse(text="".join(pieces), provider=self.name, model=self.model)

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
            messages = [
                self._convert_message(
                    message
                )
                for message in request.messages
            ]
            return self._with_images(messages, request)

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

        return self._with_images(messages, request)

    @staticmethod
    def _with_images(messages, request):
        if request.images:
            user = next((message for message in reversed(messages) if message.get("role") == "user"), None)
            if user is None:
                raise ValueError("A screenshot requires a user message.")
            user["content"] = [{"type": "text", "text": str(user.get("content", ""))}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + data}} for data in request.images]
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
