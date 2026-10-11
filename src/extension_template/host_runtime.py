import re
from typing import Any, Literal
from urllib.parse import quote

import httpx

from .errors import ExtensionError
from .settings import Settings

MemoryScope = Literal["session_memory", "profile_memory", "episodic_memory"]


class HostRuntimeClient:
    """Server-side adapter to the generic runtime. Use as an async context manager.

    No retries: generation, memory writes and voice control may have side effects.
    The transport argument is a test seam; production uses actual HTTP.
    """

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        settings.require_host_key()
        self._prefix = f"/v1/extensions/{quote(settings.extension_id, safe='')}/runtime"
        self._http = httpx.AsyncClient(
            base_url=settings.host_base_url.rstrip("/"),
            headers={"X-API-Key": settings.host_api_key},
            timeout=settings.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> "HostRuntimeClient":
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    async def _request(self, method: str, suffix: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._http.request(method, self._prefix + suffix, **kwargs)
        except httpx.TimeoutException as exc:
            raise ExtensionError("E_HOST_TIMEOUT", "Orket request timed out.", status=504) from exc
        except httpx.RequestError as exc:
            raise ExtensionError("E_HOST_UNREACHABLE", "Could not reach the Orket host.") from exc
        if response.status_code in {401, 403}:
            raise ExtensionError("E_HOST_AUTH", "Orket rejected the configured host credentials.", status=503)
        if 500 <= response.status_code < 600:
            # A host-wide condition, not something about this request: Orket
            # 0.8.2 surfaced a model timeout as a bare 500 (McElyea/Orket#6),
            # and 0.8.4 returns a typed 504/503 for a timeout or an
            # unavailable model.
            raise ExtensionError("E_HOST_SERVER", _http_failure(response))
        if not 200 <= response.status_code < 300:
            raise ExtensionError("E_HOST_HTTP", _http_failure(response))
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExtensionError("E_HOST_RESPONSE", "Orket returned invalid JSON.") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise ExtensionError("E_HOST_RESPONSE", "Orket did not return a successful runtime response.")
        return payload

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/status")

    async def models(self, *, provider: str = "") -> dict[str, Any]:
        return await self._request("GET", "/models", params={"provider": provider})

    async def generate(
        self,
        *,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop_sequences: list[str] | None = None,
        provider: str = "",
        model: str = "",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/llm/generate",
            json={
                "system_prompt": system_prompt,
                "user_message": user_message,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop_sequences": stop_sequences or [],
                "provider": provider,
                "model": model,
            },
        )

    async def memory_query(
        self,
        *,
        scope: MemoryScope,
        session_id: str = "",
        query: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/memory/query",
            json={
                "scope": scope,
                "session_id": session_id,
                "query": query,
                "limit": limit,
            },
        )

    async def memory_write(
        self,
        *,
        scope: MemoryScope,
        key: str,
        value: str,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/memory/write",
            json={
                "scope": scope,
                "key": key,
                "value": value,
                "session_id": session_id,
                "metadata": metadata or {},
            },
        )

    async def memory_clear(
        self,
        *,
        scope: Literal["session_memory", "episodic_memory"],
        session_id: str,
    ) -> dict[str, Any]:
        return await self._request("POST", "/memory/clear", json={"scope": scope, "session_id": session_id})

    async def voice_state(self) -> dict[str, Any]:
        return await self._request("GET", "/voice/state")

    async def voice_control(
        self,
        *,
        command: Literal["start", "stop", "submit"],
        silence_delay_sec: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": command}
        if silence_delay_sec is not None:
            payload["silence_delay_sec"] = silence_delay_sec
        return await self._request("POST", "/voice/control", json=payload)

    async def transcribe(
        self,
        *,
        audio_b64: str,
        mime_type: str = "audio/wav",
        language_hint: str = "",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/voice/transcribe",
            json={
                "audio_b64": audio_b64,
                "mime_type": mime_type,
                "language_hint": language_hint,
            },
        )

    async def voices(self) -> dict[str, Any]:
        return await self._request("GET", "/tts/voices")

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str = "",
        emotion_hint: str = "neutral",
        speed: float = 1.0,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/tts/synthesize",
            json={
                "text": text,
                "voice_id": voice_id,
                "emotion_hint": emotion_hint,
                "speed": speed,
            },
        )


_TYPED_CODE = re.compile(r"^E_[A-Z0-9_]{1,80}$")
# A typed Orket message such as `E_MODEL_INPUT_BUDGET: utf8_byte_estimate=17051,
# input_limit=8192; ...`: names, numbers and punctuation only. Anything else
# falls back to the code alone, so free text from upstream never comes through.
_PLAIN_MESSAGE = re.compile(r"^[A-Za-z0-9_=:;,. ()/-]+$")


def _http_failure(response: httpx.Response) -> str:
    """`Orket returned HTTP <status>.`, plus Orket's own typed reason when it
    gave one. Since 0.8.3/0.8.4 the runtime API answers a refused request
    with `detail: {ok: false, code, message}`. For example, `E_MODEL_INPUT_BUDGET`
    with the estimate and the limits is the only way to tell that the host's
    profile is too small for the prompt. Only that typed shape is used, and
    its message only when it is plain names, numbers and punctuation: an
    arbitrary response body is never echoed back."""
    text = f"Orket returned HTTP {response.status_code}."
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return text
    if not isinstance(detail, dict):
        return text
    code, message = detail.get("code"), detail.get("message")
    if not isinstance(code, str) or not _TYPED_CODE.match(code):
        return text
    reason = code
    if isinstance(message, str) and message.startswith(code):
        flat = " ".join(message.split())[:400]
        if _PLAIN_MESSAGE.match(flat):
            reason = flat
    return f"{text[:-1]}: {reason}"
