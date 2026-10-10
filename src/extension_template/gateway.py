"""Optional headless HTTP adapter; install the gateway extra to use it."""

import hmac
import ipaddress
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .domain import GenerateInput
from .errors import ExtensionError
from .host_runtime import HostRuntimeClient
from .service import ExtensionService
from .settings import Settings

MAX_BODY_BYTES = 65536


class GatewayPolicy:
    """Authenticate and bound bodies before routing or JSON decoding."""

    def __init__(self, app, *, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            local = ipaddress.ip_address((scope.get("client") or ("", 0))[0]).is_loopback
        except ValueError:
            local = False
        headers = dict(scope["headers"])
        supplied = headers.get(b"authorization", b"")
        if not local or not hmac.compare_digest(supplied, self.expected):
            error = ExtensionError(
                "E_GATEWAY_AUTH", "Local connection and bearer token required.", status=401
            )
            await JSONResponse(error.as_dict(), status_code=error.status)(scope, receive, send)
            return
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if len(body) > MAX_BODY_BYTES:
                error = ExtensionError("E_BODY_TOO_LARGE", "Request body exceeds 65536 bytes.", status=413)
                await JSONResponse(error.as_dict(), status_code=error.status)(scope, receive, send)
                return
            if not event.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(settings: Settings, *, transport=None) -> FastAPI:
    settings.require_host_key()
    if len(settings.gateway_token) < 32 or settings.gateway_token == settings.host_api_key:
        raise ExtensionError(
            "E_GATEWAY_TOKEN", "Set a distinct EXTENSION_GATEWAY_TOKEN of at least 32 characters.", status=503
        )

    @asynccontextmanager
    async def lifespan(app):
        async with HostRuntimeClient(settings, transport=transport) as host:
            app.state.host = host
            app.state.service = ExtensionService(host)
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(GatewayPolicy, token=settings.gateway_token)

    @app.exception_handler(ExtensionError)
    async def runtime_error(_request: Request, exc: ExtensionError):
        return JSONResponse(exc.as_dict(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def input_error(_request: Request, _exc: RequestValidationError):
        error = ExtensionError("E_INPUT", "Invalid request payload.", status=422)
        return JSONResponse(error.as_dict(), status_code=error.status)

    @app.get("/api/status")
    async def status(request: Request):
        return await request.app.state.host.status()

    @app.get("/api/models")
    async def models(request: Request, provider: str = ""):
        return await request.app.state.host.models(provider=provider)

    @app.post("/api/generate")
    async def generate(payload: GenerateInput, request: Request):
        return await request.app.state.service.generate(payload)

    return app
