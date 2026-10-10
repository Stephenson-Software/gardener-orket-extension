from typing import Any

from .domain import (
    AUDIT_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    AuditInput,
    GenerateInput,
    audit_message,
    cited_sources,
    require_output,
)
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
        return {
            "ok": True,
            "text": require_output(_text(result)),
            "model": result.get("model"),
            "latency_ms": result.get("latency_ms"),
        }

    async def audit(self, request: AuditInput) -> dict[str, Any]:
        """One report over a bounded snapshot. Orket selects and calls the model."""
        result = await self.host.generate(
            system_prompt=AUDIT_SYSTEM_PROMPT.format(words=request.report_words),
            user_message=audit_message(request),
            provider=request.provider,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=0,
        )
        report = require_output(_text(result))
        return {
            "ok": True,
            "report": report,
            "source_refs": cited_sources(report, request),
            "model": result.get("model"),
            "latency_ms": result.get("latency_ms"),
            "input_tokens": result.get("input_tokens"),
            "output_tokens": result.get("output_tokens"),
        }


def _text(result: dict[str, Any]) -> str:
    text = result.get("text")
    if not isinstance(text, str):
        raise ExtensionError("E_HOST_RESPONSE", "Orket generation response is missing text.")
    return text
