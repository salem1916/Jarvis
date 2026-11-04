"""Public Responses API using user-authorized ChatGPT plan usage, not API credits."""

import json
import re

import httpx

from jarvis.core.request_control import check_cancelled, current_control
from jarvis.models.base import ModelProvider, ModelRequest, ModelResponse
from jarvis.models.cancellable_http import provider_client
from jarvis.models.chatgpt_account import RESOURCE, ChatGPTAccount
from jarvis.models.connection_errors import (
    ProviderConnectionError,
    check_provider_response,
    network_failure,
)


class ChatGPTPlanProvider(ModelProvider):
    name = "chatgpt_plan"

    def __init__(self, account: ChatGPTAccount, model: str) -> None:
        if not model:
            raise ValueError("Select a model from your ChatGPT account in Settings.")
        self.account = account
        self.model = model

    def generate(self, request: ModelRequest) -> ModelResponse:
        try:
            return self._generate(request)
        except httpx.RequestError as error:
            raise network_failure(self.name, error) from error

    def _generate(self, request: ModelRequest) -> ModelResponse:
        if request.tools:
            raise ValueError("ChatGPT plan reasoning does not expose PC tools. Use the trusted action route.")
        instructions = "\n\n".join(m.content for m in request.messages if m.role == "system") or request.system_prompt
        messages: list[dict[str, object]] = [{"role": m.role, "content": m.content} for m in request.messages
                    if m.role in {"user", "assistant"} and m.content]
        if not messages:
            messages.append({"role": "user", "content": request.prompt})
        if request.json_output:
            # Responses validates JSON mode against input messages, not only
            # the separate instructions field. Keep this in the user content
            # so it also survives conversion to multimodal image input.
            user = next((message for message in reversed(messages) if message["role"] == "user"), None)
            if user is None:
                messages.append({"role": "user", "content": "Return the result as JSON."})
            else:
                user["content"] = "Return the result as JSON.\n" + str(user["content"])
        if request.images:
            user = next((message for message in reversed(messages) if message["role"] == "user"), None)
            if user is None:
                raise ValueError("A screen image requires a user message.")
            user["content"] = [{"type": "input_text", "text": str(user["content"])}] + [
                {"type": "input_image", "image_url": "data:image/png;base64," + data} for data in request.images]
        payload: dict[str, object] = {"model": self.model, "input": messages, "store": False, "stream": True}
        if instructions:
            payload["instructions"] = instructions
        if self.model.startswith("gpt-6"):
            payload["reasoning"] = {"effort": "low"}
        if request.json_output:
            payload["text"] = {"format": {"type": "json_object"}}
        check_cancelled()
        token = self.account.access_token()
        parts: list[str] = []
        completed = False
        control = current_control()
        with (
            provider_client(timeout=httpx.Timeout(30, connect=5), transport=self.account.transport) as client,
            client.stream("POST", RESOURCE + "/responses",
                               headers={"Authorization": "Bearer " + token},
                               json=payload) as response,
        ):
            if response.status_code == 401:
                raise ProviderConnectionError("ChatGPT needs to reconnect. Open Settings → Accounts.", status_code=401)
            if response.status_code in {402, 403, 429}:
                raise ProviderConnectionError("ChatGPT plan usage is unavailable or limited. Check Manage usage in Settings.", status_code=response.status_code)
            check_provider_response(response, self.name)
            for line in response.iter_lines():
                check_cancelled()
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    continue
                event = json.loads(raw)
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    delta = event.get("delta", "")
                    parts.append(delta)
                    if control:
                        control.emit(delta)
                elif kind in {"response.failed", "response.incomplete", "error"}:
                    state = event.get("response", {})
                    detail = state.get("error") or event.get("error") or state.get("incomplete_details") or {}
                    reason = detail.get("message") or detail.get("reason") or detail.get("code") or kind
                    safe = re.sub(r"data:image/[^\s]+|Bearer\s+\S+", "[redacted]", str(reason))[:260]
                    raise ProviderConnectionError("ChatGPT did not complete this reply: " + safe)
                elif kind == "response.completed":
                    if event.get("response", {}).get("status", "completed") != "completed":
                        raise ValueError("ChatGPT response did not finish successfully.")
                    completed = True
                    if not parts:
                        for item in event.get("response", {}).get("output", []):
                            parts.extend(part["text"] for part in item.get("content", [])
                                         if part.get("type") == "output_text" and isinstance(part.get("text"), str))
                    break  # Completion is authoritative; never wait on an idle SSE socket.
        if not completed:
            raise ValueError("ChatGPT's stream ended before completion. Retry or check Manage usage.")
        if not any(parts):
            raise ValueError("ChatGPT completed without a text reply. No task completion is claimed.")
        return ModelResponse(text="".join(parts), provider=self.name, model=self.model)
