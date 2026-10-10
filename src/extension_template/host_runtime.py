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
        if not 200 <= response.status_code < 300:
            raise ExtensionError("E_HOST_HTTP", f"Orket returned HTTP {response.status_code}.")
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
