from typing import Any

from orket_extension_sdk.llm import GenerateRequest
from orket_extension_sdk.result import WorkloadResult
from orket_extension_sdk.workload import WorkloadContext

from .domain import SYSTEM_PROMPT, GenerateInput, require_output


def run(ctx: WorkloadContext, payload: dict[str, Any]) -> WorkloadResult:
    """Host-dispatched workload uses injected SDK capabilities, never HTTP back into its host."""
    request = GenerateInput.model_validate(payload)
    if request.provider or request.model:
        raise ValueError("Configure model/provider on the host for SDK workloads, not in the payload.")
    result = ctx.capabilities.llm().generate(
        GenerateRequest(
            system_prompt=SYSTEM_PROMPT,
            user_message=request.message,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
    )
    return WorkloadResult(
        ok=True,
        output={
            "text": require_output(result.text),
            "model": result.model,
            "latency_ms": result.latency_ms,
        },
    )
