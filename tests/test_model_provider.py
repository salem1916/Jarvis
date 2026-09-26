from jarvis.models.base import ModelProvider, ModelRequest, ModelResponse


class DummyModelProvider(ModelProvider):
    name = "dummy"

    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text=f"Response to: {request.prompt}",
            provider=self.name,
            model="dummy-model",
        )


def test_model_request_stores_prompt():
    request = ModelRequest(
        prompt="Hello JARVIS",
    )

    assert request.prompt == "Hello JARVIS"
    assert request.system_prompt is None


def test_model_provider_generates_response():
    provider = DummyModelProvider()

    request = ModelRequest(
        prompt="Hello",
    )

    response = provider.generate(request)

    assert response.text == "Response to: Hello"
    assert response.provider == "dummy"
    assert response.model == "dummy-model"