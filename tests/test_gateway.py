import json

import httpx
import pytest

pytest.importorskip("fastapi", reason="Install the gateway extra for optional adapter coverage")
from fastapi.testclient import TestClient  # noqa: E402

from extension_template.errors import ExtensionError  # noqa: E402
from extension_template.gateway import create_app  # noqa: E402
from extension_template.settings import Settings  # noqa: E402

pytestmark = pytest.mark.integration
TOKEN = "gateway-" + "x" * 32
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def app(seen):
    def handler(request):
        seen.append(request)
        assert request.headers["X-API-Key"] == "host-secret"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"ok": True, "text": "reply", "model": "test"})

    return create_app(
        Settings(host_api_key="host-secret", gateway_token=TOKEN), transport=httpx.MockTransport(handler)
    )


def test_gateway_auth_and_service_route():
    seen = []
    with TestClient(app(seen), client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/status").status_code == 401
        assert client.get("/api/status", headers={"Authorization": "Bearer host-secret"}).status_code == 401
        response = client.post("/api/generate", headers=HEADERS, json={"message": "hello"})
        assert response.status_code == 200 and response.json()["text"] == "reply"
    assert len(seen) == 1
    assert seen[0].url.path.endswith("/runtime/llm/generate")
    assert json.loads(seen[0].content)["user_message"] == "hello"


def test_gateway_blocks_nonlocal_caller_and_ignores_forwarded_headers():
    seen = []
    with TestClient(app(seen), client=("203.0.113.1", 50000)) as client:
        assert (
            client.get("/api/status", headers={**HEADERS, "X-Forwarded-For": "127.0.0.1"}).status_code == 401
        )
    assert seen == []


def test_gateway_rejects_invalid_and_oversized_bodies_before_host_call():
    seen = []
    with TestClient(app(seen), client=("127.0.0.1", 50000)) as client:
        invalid = client.post("/api/generate", headers=HEADERS, json={"message": " ", "secret": "private"})
        assert invalid.status_code == 422
        assert "private" not in invalid.text
        oversized = client.post("/api/generate", headers=HEADERS, content=b"x" * 65537)
        assert oversized.status_code == 413
    assert seen == []


@pytest.mark.parametrize("token", ["", "short", "host-secret"])
def test_gateway_requires_a_separate_token(token):
    with pytest.raises(ExtensionError, match="distinct EXTENSION_GATEWAY_TOKEN"):
        create_app(Settings(host_api_key="host-secret", gateway_token=token))
