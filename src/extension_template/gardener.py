"""gardener's ``command`` harness contract, served through the Orket host.

gardener (https://github.com/Stephenson-Software/gardener) runs this command
in the target repository's clone with the prompt on stdin and
``GARDENER_HARNESS_MODE``/``GARDENER_HARNESS_SPEC``/``GARDENER_HARNESS_MODEL``/
``GARDENER_HARNESS_TIMEOUT`` in the environment, and reads one JSON object from
stdout (gardener ``docs/HARNESSES.md``). Only report mode is served: there are
no tools to scope, because the model only ever receives a read-only snapshot.
"""

import json
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .domain import AuditInput, AuditSource
from .errors import ExtensionError
from .host_runtime import HostRuntimeClient
from .service import ExtensionService
from .settings import Settings
from .snapshot import SnapshotLimits, collect_sources

MAX_PROMPT_CHARS = 64_000
# Failures that say this device cannot reach or use its Orket host, so every
# repository in a gardener overnight batch would fail identically.
DEVICE_ERRORS = frozenset({"E_HOST_UNREACHABLE", "E_HOST_AUTH", "E_HOST_KEY_REQUIRED", "E_CONFIG_URL"})


def envelope(result: str, *, is_error: bool, session_id: str | None = None, blocked: bool = False) -> dict:
    return {"result": result, "is_error": is_error, "session_id": session_id,
            "total_cost_usd": 0, "permission_denials": [], "blocked": blocked}


def _int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = str(environ.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as exc:
        raise ExtensionError("E_CONFIG", f"{name} must be a whole number.", status=503) from exc
    if value <= 0:
        raise ExtensionError("E_CONFIG", f"{name} must be positive.", status=503)
    return value


def snapshot_limits(environ: Mapping[str, str]) -> SnapshotLimits:
    docs = str(environ.get("GARDENER_ORKET_DOCS") or "").strip()
    return SnapshotLimits(
        max_total_bytes=_int(environ, "GARDENER_ORKET_MAX_TOTAL_BYTES", 24_000),
        max_file_bytes=_int(environ, "GARDENER_ORKET_MAX_FILE_BYTES", 6_000),
        max_listed_files=_int(environ, "GARDENER_ORKET_MAX_FILES", 400),
        **({"docs": tuple(d.strip() for d in docs.split(",") if d.strip())} if docs else {}),
    )


def audit_request(prompt: str, cwd: Path, environ: Mapping[str, str]) -> AuditInput:
    try:
        spec = json.loads(str(environ.get("GARDENER_HARNESS_SPEC") or "{}"))
    except json.JSONDecodeError as exc:
        raise ExtensionError("E_CONFIG", "GARDENER_HARNESS_SPEC is not JSON.", status=503) from exc
    roots = [Path(item) for item in spec.get("add_dirs", [])] if isinstance(spec, dict) else []
    sources = collect_sources(prompt, cwd, roots, snapshot_limits(environ))
    return AuditInput(
        task=prompt,
        sources=[AuditSource(ref=s.ref, path=s.path, text=s.text) for s in sources],
        provider=str(environ.get("GARDENER_ORKET_PROVIDER") or "").strip(),
        model=str(environ.get("GARDENER_HARNESS_MODEL") or "").strip(),
        max_tokens=_int(environ, "GARDENER_ORKET_MAX_TOKENS", 1024),
        report_words=_int(environ, "GARDENER_ORKET_REPORT_WORDS", 250),
    )


def render(result: dict[str, Any], request: AuditInput, settings: Settings) -> str:
    paths = {source.ref: source.path for source in request.sources}
    cited = ", ".join(f"{ref} ({paths[ref]})" for ref in result["source_refs"])
    return (f"{result['report'].rstrip()}\n\n---\nGenerated through the Orket host at "
            f"{settings.host_base_url} (extension `{settings.extension_id}`, model `{result.get('model')}`); "
            f"every citation was checked against the supplied snapshot. Sources cited: {cited}.")


async def dispatch(
    prompt: str, cwd: Path, environ: Mapping[str, str], settings: Settings
) -> tuple[dict, int]:
    """Run one gardener dispatch. Returns gardener's envelope and the exit code."""
    mode = str(environ.get("GARDENER_HARNESS_MODE") or "").strip()
    if mode != "report":
        return envelope(f"this harness serves report mode only, not {mode!r}", is_error=True), 2
    if len(prompt) > MAX_PROMPT_CHARS:
        return envelope(f"prompt exceeds {MAX_PROMPT_CHARS} characters", is_error=True), 2
    session = f"orket-extension:{settings.extension_id}:{uuid.uuid4().hex[:12]}"
    try:
        request = audit_request(prompt, cwd, environ)
        async with HostRuntimeClient(settings) as host:
            result = await ExtensionService(host).audit(request)
    except ValidationError:
        return envelope("invalid audit input (empty prompt or out-of-range setting)", is_error=True), 2
    except ExtensionError as exc:
        text = f"Orket audit failed: {exc.code}: {exc.message}"
        return envelope(text, is_error=True, session_id=session, blocked=exc.code in DEVICE_ERRORS), 1
    return envelope(render(result, request, settings), is_error=False, session_id=session), 0
