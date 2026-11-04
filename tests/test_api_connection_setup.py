from unittest.mock import patch

import httpx
import pytest

from jarvis.core.config import JarvisSettings
from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_control import RequestControl, request_scope
from jarvis.models.base import ModelRequest
from jarvis.models.connection_errors import ProviderConnectionError
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.runtime.intelligence import IntelligenceHub


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("status,expected", [(401, "rejected this key"), (403, "Access was denied"),
                                             (404, "Load available models"), (429, "quota exhausted")])
def test_chat_errors_are_actionable_and_do_not_expose_credentials(stream, status, expected):
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json={"error": "secret-test-key"}))
    provider = OpenAICompatibleProvider(provider_name="gemini", model="unavailable", api_key="secret-test-key",
                                        base_url="https://example.test", transport=transport)
    with (request_scope(RequestControl(on_delta=(lambda _: None) if stream else None)),
          pytest.raises(ProviderConnectionError, match=expected) as error):
        provider.generate(ModelRequest(prompt="hello"))
    assert "secret-test-key" not in str(error.value)
    assert "HTTP " + str(status) in str(error.value)


def test_gemini_model_list_removes_native_resource_prefix_and_keeps_auth_key_intact():
    hub = IntelligenceHub(JarvisSettings(gemini_api_key="AQ.fake-test-key"), PersonalMemory())
    def handle(request):
        assert request.headers["Authorization"] == "Bearer AQ.fake-test-key"
        return httpx.Response(200, json={"data": [{"id": "models/gemini-flash-latest"}, None]})
    client = httpx.Client(transport=httpx.MockTransport(handle))
    with patch("jarvis.runtime.intelligence.httpx.Client", return_value=client):
        assert hub.list_models("gemini") == [{"id": "gemini-flash-latest", "name": "gemini-flash-latest"}]


def test_model_catalog_authentication_error_explains_invalid_key():
    hub = IntelligenceHub(JarvisSettings(groq_api_key="fake-groq-key"), PersonalMemory())
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    with (patch("jarvis.runtime.intelligence.httpx.Client", return_value=client),
          pytest.raises(ProviderConnectionError, match="rejected this key")):
        hub.list_models("groq")


def test_connection_failure_does_not_show_request_url_or_key():
    def handle(request):
        raise httpx.ConnectError("sensitive internal URL fake-key", request=request)
    provider = OpenAICompatibleProvider(provider_name="groq", model="test", api_key="fake-key",
                                        base_url="https://example.test", transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderConnectionError, match="internet connection") as error:
        provider.generate(ModelRequest(prompt="hello"))
    assert "fake-key" not in str(error.value)
