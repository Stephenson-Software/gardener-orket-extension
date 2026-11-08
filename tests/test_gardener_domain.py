"""Audit rules and the read-only snapshot, without a host or model."""

import subprocess

import pytest
from pydantic import ValidationError

from extension_template.domain import AuditInput, AuditSource, audit_message, cited_sources
from extension_template.errors import ExtensionError
from extension_template.gardener import envelope, render, snapshot_limits
from extension_template.settings import Settings
from extension_template.snapshot import SnapshotLimits, collect_sources

pytestmark = pytest.mark.unit


def _request(*refs: str) -> AuditInput:
    return AuditInput(task="Audit.", sources=[AuditSource(ref=r, path=f"{r}.md", text="t") for r in refs])


def test_citations_must_exist_and_come_from_the_snapshot():
    request = _request("src01", "src02", "listing")
    assert cited_sources("A gap [src02]. Another [src01] and [src02]. Files [listing].", request) == [
        "src02", "src01", "listing"]
    with pytest.raises(ExtensionError) as unsourced:
        cited_sources("A confident claim with no citation.", request)
    assert unsourced.value.code == "E_REPORT_UNSOURCED"
    with pytest.raises(ExtensionError) as unknown:
        cited_sources("A gap [src01] and an invented one [src09].", request)
    assert unknown.value.code == "E_REPORT_UNKNOWN_SOURCE"


def test_a_cited_listing_that_was_not_supplied_is_an_unknown_source():
    """The gardener command always supplies a listing, but a service caller
    building AuditInput directly need not (#30)."""
    with pytest.raises(ExtensionError) as unknown:
        cited_sources("A gap [src01]. Files [listing].", _request("src01"))
    assert unknown.value.code == "E_REPORT_UNKNOWN_SOURCE"
    assert "listing" in unknown.value.message


@pytest.mark.parametrize("task", ["", " ", "\n\t\n"])
def test_a_task_that_is_empty_after_stripping_is_refused(task):
    with pytest.raises(ValidationError):
        AuditInput(task=task, sources=[AuditSource(ref="src01", path="a.md", text="t")])


def test_a_directly_built_audit_input_requests_the_packaged_profile_output_ceiling():
    # 1024, the old default, is refused by Ollama's qwen profile (768).
    assert _request("src01").max_tokens == 768


def test_audit_message_heads_each_source_with_its_reference():
    message = audit_message(_request("src01", "listing"))
    assert message.startswith("## Task\n\nAudit.")
    assert "## Source [src01] src01.md\n\nt" in message and "## Source [listing] listing.md" in message


def test_the_footer_names_the_model_the_host_reported():
    result = {"report": "A gap [src01].", "source_refs": ["src01"], "model": "simulated-model"}
    footer = render(result, _request("src01"), Settings())
    assert "model `simulated-model`" in footer and "not reported" not in footer


@pytest.mark.parametrize("reported", [{}, {"model": None}, {"model": ""}])
def test_the_footer_states_an_unknown_model_instead_of_inventing_a_name(reported):
    result = {"report": "A gap [src01].", "source_refs": ["src01"], **reported}
    footer = render(result, _request("src01"), Settings())
    assert "model not reported by the host" in footer
    assert "None" not in footer and "model ``" not in footer


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    (repo / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    for argv in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)
    return repo


def test_snapshot_takes_prompt_named_files_only_from_allowed_roots(tmp_path):
    repo = _repo(tmp_path)
    conventions = tmp_path / "conventions"
    conventions.mkdir()
    (conventions / "CHECKLIST.md").write_text("1. README exists.\n", encoding="utf-8")
    secret = tmp_path / "elsewhere.txt"
    secret.write_text("not for the model\n", encoding="utf-8")
    prompt = f"Read {conventions / 'CHECKLIST.md'} and {secret}."
    sources = collect_sources(prompt, repo, [conventions], SnapshotLimits())
    assert [s.ref for s in sources] == ["src01", "src02", "listing"]
    assert sources[0].path == str((conventions / "CHECKLIST.md").resolve())
    assert sources[1].path == "README.md"
    assert sources[2].text.splitlines() == ["README.md", "main.c"]
    assert all("not for the model" not in s.text for s in sources)


def test_snapshot_respects_byte_budgets(tmp_path):
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("x" * 5000, encoding="utf-8")
    sources = collect_sources("", repo, [], SnapshotLimits(max_total_bytes=1000, max_file_bytes=300))
    assert sources[0].text == "x" * 300 + "\n[truncated]"


def test_envelope_and_limits_follow_gardeners_contract():
    assert envelope("r", is_error=False) == {"result": "r", "is_error": False, "session_id": None,
                                             "total_cost_usd": 0, "permission_denials": [], "blocked": False}
    limits = snapshot_limits({"GARDENER_ORKET_MAX_TOTAL_BYTES": "8000", "GARDENER_ORKET_DOCS": "A.md, B.md"})
    assert limits.max_total_bytes == 8000 and limits.docs == ("A.md", "B.md")
    with pytest.raises(ExtensionError):
        snapshot_limits({"GARDENER_ORKET_MAX_FILES": "0"})
