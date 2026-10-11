import asyncio
import json

import httpx
import pytest

from extension_template.domain import GenerateInput
from extension_template.errors import ExtensionError
from extension_template.host_runtime import HostRuntimeClient
from extension_template.service import ExtensionService
from extension_template.settings import Settings

pytestmark = pytest.mark.contract

OPERATIONS = [
    ("status", {}, "GET", "/status", None),
    ("models", {"provider": "ollama"}, "GET", "/models", None),
    (
        "generate",
        {"system_prompt": "system", "user_message": "hello"},
        "POST",
        "/llm/generate",
        {
            "system_prompt": "system",
            "user_message": "hello",
            "max_tokens": 512,
            "temperature": 0.2,
            "stop_sequences": [],
            "provider": "",
            "model": "",
        },
    ),
    (
        "memory_query",
        {"scope": "session_memory", "session_id": "s"},
        "POST",
        "/memory/query",
        {"scope": "session_memory", "session_id": "s", "query": "", "limit": 10},
    ),
    (
        "memory_write",
        {"scope": "session_memory", "session_id": "s", "key": "k", "value": "v"},
        "POST",
        "/memory/write",
        {"scope": "session_memory", "session_id": "s", "key": "k", "value": "v", "metadata": {}},
    ),
    (
        "memory_clear",
        {"scope": "session_memory", "session_id": "s"},
        "POST",
        "/memory/clear",
        {"scope": "session_memory", "session_id": "s"},
    ),
    ("voice_state", {}, "GET", "/voice/state", None),
    ("voice_control", {"command": "submit"}, "POST", "/voice/control", {"command": "submit"}),
    (
        "transcribe",
        {"audio_b64": "YQ=="},
        "POST",
        "/voice/transcribe",
        {"audio_b64": "YQ==", "mime_type": "audio/wav", "language_hint": ""},
    ),
    ("voices", {}, "GET", "/tts/voices", None),
    (
        "synthesize",
        {"text": "hi"},
        "POST",
        "/tts/synthesize",
        {"text": "hi", "voice_id": "", "emotion_hint": "neutral", "speed": 1.0},
    ),
]


@pytest.mark.parametrize("operation,kwargs,method,suffix,body", OPERATIONS)
def test_runtime_routes_and_credentials(operation, kwargs, method, suffix, body):
    seen = []

    def host(request):
        seen.append(request)
        assert request.method == method
        assert request.url.path == f"/v1/extensions/example.test/runtime{suffix}"
        assert request.headers["X-API-Key"] == "host-secret"
        if body is not None:
            assert json.loads(request.content) == body
        if operation == "models":
            assert request.url.params["provider"] == "ollama"
        return httpx.Response(200, json={"ok": True})

    async def run():
        settings = Settings(extension_id="example.test", host_api_key="host-secret")
        async with HostRuntimeClient(settings, transport=httpx.MockTransport(host)) as client:
            assert await getattr(client, operation)(**kwargs) == {"ok": True}

    asyncio.run(run())
    assert len(seen) == 1


@pytest.mark.parametrize(
    "response,code,status",
    [
        (httpx.Response(401, text="host-secret"), "E_HOST_AUTH", 503),
        (httpx.Response(403, text="host-secret"), "E_HOST_AUTH", 503),
        (httpx.Response(500, text="host-secret"), "E_HOST_SERVER", 502),
        (httpx.Response(503, text="host-secret"), "E_HOST_SERVER", 502),
        (httpx.Response(404, text="host-secret"), "E_HOST_HTTP", 502),
        (httpx.Response(302, headers={"Location": "https://other.example/"}), "E_HOST_HTTP", 502),
        (httpx.Response(200, text="not json"), "E_HOST_RESPONSE", 502),
        (httpx.Response(200, json=[]), "E_HOST_RESPONSE", 502),
        (httpx.Response(200, json={"ok": False, "detail": "host-secret"}), "E_HOST_RESPONSE", 502),
    ],
)
def test_upstream_failure_is_safe_and_never_retried(response, code, status):
    seen = []

    def handler(request):
        seen.append(request)
        return response

    async def run():
        async with HostRuntimeClient(
            Settings(host_api_key="host-secret"), transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(ExtensionError) as error:
                await client.status()
            assert error.value.code == code
            assert error.value.status == status
            assert "host-secret" not in json.dumps(error.value.as_dict())

    asyncio.run(run())
    assert len(seen) == 1


@pytest.mark.parametrize(
    "response,code,expected,absent",
    [
        # Orket 0.8.3+: the host's profile is too small for the prompt.
        (httpx.Response(400, json={"detail": {"ok": False, "code": "E_MODEL_INPUT_BUDGET",
                                              "message": "E_MODEL_INPUT_BUDGET: utf8_byte_estimate=17051, "
                                                         "input_limit=8192, context_limit=8192"}}),
         "E_HOST_HTTP", "HTTP 400: E_MODEL_INPUT_BUDGET: utf8_byte_estimate=17051, input_limit=8192", None),
        # Orket 0.8.4: a typed model timeout is still a host-wide failure.
        (httpx.Response(504, json={"detail": {
            "ok": False, "code": "E_EXTENSION_MODEL_PROVIDER_TIMEOUT",
            "message": "E_EXTENSION_MODEL_PROVIDER_TIMEOUT: model timed out"}}),
         "E_HOST_SERVER", "HTTP 504: E_EXTENSION_MODEL_PROVIDER_TIMEOUT", None),
        # A message that is not plain falls back to the code alone.
        (httpx.Response(400, json={"detail": {"ok": False, "code": "E_SOMETHING",
                                              "message": "E_SOMETHING: <host-secret> {\"k\": 1}"}}),
         "E_HOST_HTTP", "HTTP 400: E_SOMETHING", "host-secret"),
        # A message that does not start with its code is never shown.
        (httpx.Response(400, json={"detail": {"ok": False, "code": "E_SOMETHING", "message": "host-secret"}}),
         "E_HOST_HTTP", "HTTP 400: E_SOMETHING", "host-secret"),
        # A code that is not a typed code is ignored entirely.
        (httpx.Response(400, json={"detail": {"ok": False, "code": "host-secret", "message": "host-secret"}}),
         "E_HOST_HTTP", "Orket returned HTTP 400.", "host-secret"),
        (httpx.Response(400, json={"detail": "host-secret"}), "E_HOST_HTTP", "Orket returned HTTP 400.",
         "host-secret"),
    ],
)
def test_orkets_typed_reason_is_passed_on_and_nothing_else(response, code, expected, absent):
    def handler(request):
        return response

    async def run():
        async with HostRuntimeClient(
            Settings(host_api_key="host-secret"), transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(ExtensionError) as error:
                await client.status()
            assert error.value.code == code
            assert expected in error.value.message
            if absent:
                assert absent not in json.dumps(error.value.as_dict())

    asyncio.run(run())


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ReadTimeout, "E_HOST_TIMEOUT"),
        (httpx.ConnectError, "E_HOST_UNREACHABLE"),
    ],
)
def test_transport_failures_are_safe(exception, code):
    def handler(request):
        raise exception("host-secret", request=request)

    async def run():
        async with HostRuntimeClient(
            Settings(host_api_key="host-secret"), transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(ExtensionError) as error:
                await client.status()
            assert error.value.code == code
            assert "host-secret" not in str(error.value)

    asyncio.run(run())


def test_generation_projects_response_without_inventing_measurements():
    def handler(request):
        body = json.loads(request.content)
        assert body["user_message"] == "hello"
        assert body["provider"] == "ollama"
        assert body["model"] == "test-model"
        return httpx.Response(200, json={"ok": True, "text": "reply", "model": "test-model"})

    async def run():
        async with HostRuntimeClient(
            Settings(host_api_key="secret"), transport=httpx.MockTransport(handler)
        ) as host:
            result = await ExtensionService(host).generate(
                GenerateInput(message=" hello ", provider="ollama", model="test-model")
            )
            assert result == {"ok": True, "text": "reply", "model": "test-model", "latency_ms": None}

    asyncio.run(run())


@pytest.mark.parametrize("text,code", [(None, "E_HOST_RESPONSE"), ("  ", "E_EMPTY_OUTPUT")])
def test_generation_does_not_fake_missing_output(text, code):
    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True, "text": text}))
        async with HostRuntimeClient(Settings(host_api_key="secret"), transport=transport) as host:
            with pytest.raises(ExtensionError, match=".") as error:
                await ExtensionService(host).generate(GenerateInput(message="hello"))
            assert error.value.code == code

    asyncio.run(run())
