import httpx

from jarvis.models.base import ModelProvider, ModelRequest, ModelResponse


class OllamaProvider(ModelProvider):
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

    def generate(self, request: ModelRequest) -> ModelResponse:
        messages: list[dict[str, str]] = []

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

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
    "model": self.model,
    "messages": messages,
    "stream": False,
    "think": False,
    "keep_alive": "10m",
},
                timeout=self.timeout,
            )

            response.raise_for_status()

        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Could not communicate with the Ollama server."
            ) from exc

        data = response.json()

        message = data.get("message")

        if not isinstance(message, dict):
            raise TypeError("Ollama returned an invalid response.")

        content = message.get("content")

        if not isinstance(content, str):
            raise TypeError("Ollama response did not contain text.")

        return ModelResponse(
            text=content,
            provider=self.name,
            model=self.model,
        )