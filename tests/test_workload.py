from pathlib import Path

import pytest
from orket_extension_sdk.llm import GenerateResponse
from orket_extension_sdk.testing import FakeCapabilities
from orket_extension_sdk.workload import WorkloadContext

from extension_template.workload import run

pytestmark = pytest.mark.contract


class Model:
    def __init__(self):
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return GenerateResponse(text="SDK reply", model="injected-model", latency_ms=None)

    def is_available(self):
        return True


def context(model=None):
    caps = FakeCapabilities.from_mapping({"model.generate": model} if model else {})
    return WorkloadContext(
        extension_id="example.test",
        workload_id="generate",
        run_id="test",
        workspace_root=Path("."),
        input_dir=Path("."),
        output_dir=Path("."),
        capabilities=caps,
    )


def test_workload_uses_injected_capability_and_returns_sdk_result():
    model = Model()
    result = run(context(model), {"message": " hello "})
    assert result.ok and result.output["text"] == "SDK reply"
    assert result.output["latency_ms"] is None
    assert len(model.requests) == 1
    assert model.requests[0].user_message == "hello"


def test_workload_does_not_bypass_missing_capability():
    with pytest.raises(ValueError, match="E_SDK_CAPABILITY_MISSING"):
        run(context(), {"message": "hello"})


def test_workload_does_not_silently_ignore_provider_selection():
    model = Model()
    with pytest.raises(ValueError, match="Configure model/provider on the host"):
        run(context(model), {"message": "hello", "model": "other"})
    assert model.requests == []
