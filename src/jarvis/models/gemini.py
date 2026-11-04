"""Use Google's native API for text replies; retain compatibility tool-call handling."""

import json
from typing import Any
from urllib.parse import quote

import httpx

from jarvis.core.request_control import check_cancelled, current_control
from jarvis.models.base import ModelMessage, ModelRequest, ModelResponse, ModelToolCall
from jarvis.models.cancellable_http import provider_client
from jarvis.models.connection_errors import check_provider_response, network_failure
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.models.retry import retry_gemini


class GeminiProvider(OpenAICompatibleProvider):
    native_url = "https://generativelanguage.googleapis.com/v1beta/models/"
    fast_replies = True

    @staticmethod
    def _parse_tool_call(raw_tool_call: object) -> ModelToolCall:
        call = OpenAICompatibleProvider._parse_tool_call(raw_tool_call)
        if isinstance(raw_tool_call, dict):
            extra = raw_tool_call.get("extra_content")
            google = extra.get("google") if isinstance(extra, dict) else None
            signature = google.get("thought_signature") if isinstance(google, dict) else None
            if isinstance(signature, str) and signature:
                call.provider_metadata = {"google": {"thought_signature": signature}}
        return call

    @staticmethod
    def _convert_message(message: ModelMessage) -> dict[str, object]:
        converted = OpenAICompatibleProvider._convert_message(message)
        calls = converted.get("tool_calls")
        if isinstance(calls, list):
            for original, outgoing in zip(message.tool_calls, calls, strict=True):
                google = original.provider_metadata.get("google")
                if isinstance(google, dict) and isinstance(google.get("thought_signature"), str):
                    outgoing["extra_content"] = {"google": {"thought_signature": google["thought_signature"]}}
        return converted

    def _native_payload(self, request: ModelRequest) -> dict[str, Any]:
        messages = request.messages or (
            ([ModelMessage(role="system", content=request.system_prompt)] if request.system_prompt else [])
            + [ModelMessage(role="user", content=request.prompt)]
        )
        instructions = [m.content for m in messages if m.role == "system" and m.content]
        contents = [{"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
                    for m in messages if m.role in {"user", "assistant"} and m.content]
        payload: dict[str, Any] = {"contents": contents}
        if request.images:
            user = next((item for item in reversed(contents) if item["role"] == "user"), None)
            if user is None:
                raise ValueError("A screenshot requires a user message.")
            user["parts"].extend({"inlineData": {"mimeType": "image/png", "data": data}} for data in request.images)
        if instructions:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(instructions)}]}
        if self.fast_replies:
            model = self.model.removeprefix("models/")
            if model.startswith("gemini-3"):
                payload["generationConfig"] = {"thinkingConfig": {"thinkingLevel": "LOW"}}
            elif model.startswith("gemini-2.5-flash"):
                payload["generationConfig"] = {"thinkingConfig": {"thinkingBudget": 0}}
        if request.json_output:
            payload.setdefault("generationConfig", {})["responseMimeType"] = "application/json"
        return payload

    @staticmethod
    def _text(data: dict[str, Any]) -> tuple[str, bool]:
        if data.get("error") or data.get("promptFeedback", {}).get("blockReason"):
            raise ValueError("Gemini could not complete this reply. Check the prompt or try another model.")
        candidates = data.get("candidates", [])
        if not candidates:
            return "", False
        candidate = candidates[0]
        reason = candidate.get("finishReason")
        if reason and reason != "STOP":
            raise ValueError("Gemini's reply was cut short or blocked. Partial text was not saved as a complete reply.")
        parts = candidate.get("content", {}).get("parts", [])
        if any(part.get("functionCall") for part in parts):
            raise ValueError("The text-only Gemini connection requested an unavailable action tool.")
        return "".join(str(p.get("text", "")) for p in parts if not p.get("thought")), reason == "STOP"

    def generate(self, request: ModelRequest) -> ModelResponse:
        return retry_gemini(lambda: self._generate_once(request))

    def _generate_once(self, request: ModelRequest) -> ModelResponse:
        if request.tools or any(m.role == "tool" or m.tool_calls for m in request.messages):
            return super().generate(request)
        check_cancelled()
        control = current_control()
        streaming = control is not None and control.on_delta is not None
        model = quote(self.model.removeprefix("models/"), safe="")
        url = self.native_url + model + (":streamGenerateContent?alt=sse" if streaming else ":generateContent")
        headers = {"x-goog-api-key": self.api_key}
        payload = self._native_payload(request)
        pieces: list[str] = []
        finished = False
        usage = {}
        try:
            with provider_client(timeout=httpx.Timeout(self.timeout, connect=5), transport=self.transport) as client:
                if streaming:
                    with client.stream("POST", url, headers=headers, json=payload) as response:
                        check_provider_response(response, self.name)
                        for line in response.iter_lines():
                            check_cancelled()
                            if not line.startswith("data:"):
                                continue
                            data = json.loads(line[5:].strip())
                            usage = data.get("usageMetadata", usage)
                            text, done = self._text(data)
                            pieces.append(text)
                            finished = finished or done
                            if control and text:
                                control.emit(text)
                            if done:
                                break  # Completion is authoritative; do not wait for an idle SSE socket.
                else:
                    response = client.post(url, headers=headers, json=payload)
                    check_provider_response(response, self.name)
                    data = response.json()
                    usage = data.get("usageMetadata", {})
                    text, finished = self._text(data)
                    pieces.append(text)
        except httpx.RequestError as exc:
            raise network_failure(self.name, exc) from exc
        check_cancelled()
        if not finished or not any(pieces):
            raise ValueError("Gemini ended without a complete text reply. Retry later or select another available model.")
        if self.usage_callback:
            self.usage_callback(usage, dict(response.headers))
        return ModelResponse(text="".join(pieces), provider=self.name, model=self.model)
