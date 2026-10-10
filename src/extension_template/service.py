from typing import Any

from .domain import SYSTEM_PROMPT, GenerateInput, require_output
from .errors import ExtensionError
from .host_runtime import HostRuntimeClient


class ExtensionService:
    """Product orchestration seam. CLI and optional gateway share this behavior."""

    def __init__(self, host: HostRuntimeClient) -> None:
        self.host = host

    async def generate(self, request: GenerateInput) -> dict[str, Any]:
        result = await self.host.generate(
            system_prompt=SYSTEM_PROMPT,
            user_message=request.message,
            provider=request.provider,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        text = result.get("text")
        if not isinstance(text, str):
            raise ExtensionError("E_HOST_RESPONSE", "Orket generation response is missing text.")
        return {
            "ok": True,
            "text": require_output(text),
            "model": result.get("model"),
            "latency_ms": result.get("latency_ms"),
        }
