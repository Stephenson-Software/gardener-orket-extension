"""`orket-extension gardener` over real sockets with a simulated host, not a live Orket/model.

Each test runs the CLI the way gardener's command harness does: in a target
clone, prompt on stdin, GARDENER_HARNESS_* in the environment, one JSON
envelope expected on stdout.
"""

import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def host():
    state = {"reply": "No build steps are documented [src01].", "requests": [], "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, self.headers.get("X-API-Key"), payload))
            if state["status"] != 200:
                self.send_response(state["status"])
                if state.get("detail"):
                    body = json.dumps({"detail": state["detail"]}).encode()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.end_headers()
                return
            body = json.dumps({"ok": True, "text": state["reply"], "model": "simulated-model",
                               "latency_ms": None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _clone(tmp_path):
    repo = tmp_path / "target"
    repo.mkdir()
    (repo / "README.md").write_text("# target\n", encoding="utf-8")
    for argv in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)
    return repo


def _run(repo, port, *, mode="report", prompt="Audit this repository.", extra=None, drop=()):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EXTENSION_", "ORKET_", "GARDENER_"))}
    env.update({
        "EXTENSION_HOST_API_KEY": "host-secret", "EXTENSION_HOST_BASE_URL": f"http://127.0.0.1:{port}",
        "EXTENSION_ID": "example.test", "PYTHONPATH": str(SRC),
        "GARDENER_HARNESS_MODE": mode, "GARDENER_HARNESS_MODEL": "llama3.2:3b",
        "GARDENER_HARNESS_SPEC": json.dumps({"mode": mode, "add_dirs": []}), "GARDENER_HARNESS_TIMEOUT": "60",
        **(extra or {}),
    })
    for name in drop:
        env.pop(name, None)
    proc = subprocess.run([sys.executable, "-m", "extension_template", "gardener"], cwd=repo, env=env,
                          input=prompt, text=True, capture_output=True, timeout=30)
    return proc.returncode, json.loads(proc.stdout)


def test_report_dispatch_returns_a_cited_report(host, tmp_path):
    port, state = host
    repo = _clone(tmp_path)
    status = ["git", "status", "--porcelain"]
    before = subprocess.run(status, cwd=repo, capture_output=True, text=True).stdout
    code, out = _run(repo, port)
    assert code == 0, out
    assert out["is_error"] is False and out["blocked"] is False
    assert out["result"].startswith("No build steps are documented [src01].")
    assert "Sources cited: src01 (README.md)" in out["result"]
    assert out["session_id"].startswith("orket-extension:example.test:")
    (path, key, payload), = state["requests"]
    assert path == "/v1/extensions/example.test/runtime/llm/generate" and key == "host-secret"
    assert payload["model"] == "llama3.2:3b" and payload["temperature"] == 0
    assert "## Source [src01] README.md" in payload["user_message"]
    assert "host-secret" not in json.dumps(out)
    assert subprocess.run(status, cwd=repo, capture_output=True, text=True).stdout == before


@pytest.mark.parametrize(("reply", "code"), [
    ("A confident claim with no citation.", "E_REPORT_UNSOURCED"),
    ("A gap [src01] and an invented source [src07].", "E_REPORT_UNKNOWN_SOURCE"),
])
def test_unsourced_reports_are_refused_not_returned(host, tmp_path, reply, code):
    port, state = host
    state["reply"] = reply
    exit_code, out = _run(_clone(tmp_path), port)
    assert exit_code == 1 and out["is_error"] is True and out["blocked"] is False
    assert code in out["result"] and reply not in out["result"]


@pytest.mark.parametrize("mode", ["implement", "file-issue", "tend", "create-dev-loop"])
def test_every_mode_but_report_is_refused_before_the_host_is_called(host, tmp_path, mode):
    port, state = host
    exit_code, out = _run(_clone(tmp_path), port, mode=mode)
    assert exit_code == 2 and out["is_error"] is True and "report mode only" in out["result"]
    assert state["requests"] == []


def test_an_unreachable_host_is_reported_as_blocked(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    exit_code, out = _run(_clone(tmp_path), port)
    assert exit_code == 1 and out["is_error"] is True and out["blocked"] is True
    assert "E_HOST_UNREACHABLE" in out["result"]


@pytest.mark.parametrize("status,code,blocked", [(500, "E_HOST_SERVER", True), (404, "E_HOST_HTTP", False)])
def test_a_host_server_error_is_blocked_but_a_client_error_is_not(host, tmp_path, status, code, blocked):
    """Orket 0.8.2 returns a bare 500 when the host's model call times out
    (McElyea/Orket#6). That will repeat for every repository, so it must stop
    a gardener batch; a 4xx is about this request and must not."""
    port, state = host
    state["status"] = status
    exit_code, out = _run(_clone(tmp_path), port)
    assert exit_code == 1 and out["is_error"] is True and out["blocked"] is blocked
    assert code in out["result"]


@pytest.mark.parametrize("extra,code", [
    ({"EXTENSION_HOST_BASE_URL": "ftp://example.test"}, "E_CONFIG_URL"),
    ({"EXTENSION_ID": "not an id"}, "E_CONFIG_ID"),
    ({"EXTENSION_TIMEOUT_SECONDS": "soon"}, "E_CONFIG_TIMEOUT"),
    ({"EXTENSION_TIMEOUT_SECONDS": "-1"}, "E_CONFIG_TIMEOUT"),
    ({"GARDENER_HARNESS_TIMEOUT": "soon"}, "E_CONFIG_TIMEOUT"),
    ({"GARDENER_ORKET_MAX_TOTAL_BYTES": "lots"}, "E_CONFIG_LIMIT"),
    ({"GARDENER_ORKET_MAX_FILES": "0"}, "E_CONFIG_LIMIT"),
    ({"GARDENER_ORKET_MAX_TOKENS": "9000"}, "E_CONFIG_LIMIT"),
    ({"GARDENER_ORKET_REPORT_WORDS": "10"}, "E_CONFIG_LIMIT"),
    ({"GARDENER_ORKET_PROVIDER": "p" * 65}, "E_CONFIG_LIMIT"),
    ({"GARDENER_HARNESS_MODEL": "m" * 129}, "E_CONFIG_LIMIT"),
    ({"GARDENER_HARNESS_SPEC": "not json"}, "E_CONFIG_SPEC"),
    ({"GARDENER_HARNESS_SPEC": json.dumps({"add_dirs": "/srv/conventions"})}, "E_CONFIG_SPEC"),
    ({"GARDENER_HARNESS_SPEC": json.dumps({"add_dirs": 5})}, "E_CONFIG_SPEC"),
    ({"GARDENER_HARNESS_SPEC": json.dumps({"add_dirs": [5]})}, "E_CONFIG_SPEC"),
])
def test_a_configuration_error_is_blocked_before_the_host_is_called(host, tmp_path, extra, code):
    """Settings come from the environment, which is the same for every
    repository in a gardener batch, so a bad one must stop the batch rather
    than fail each repository the same way (#3)."""
    port, state = host
    exit_code, out = _run(_clone(tmp_path), port, extra=extra)
    assert exit_code == 1 and out["is_error"] is True and out["blocked"] is True, out
    assert f"{code}:" in out["result"], out["result"]
    assert state["requests"] == []


def test_an_empty_prompt_fails_only_this_dispatch(host, tmp_path):
    """Unlike an out-of-range setting, the prompt is per dispatch, so it must
    not stop a gardener batch."""
    port, state = host
    exit_code, out = _run(_clone(tmp_path), port, prompt="")
    assert exit_code == 2 and out["is_error"] is True and out["blocked"] is False, out
    assert "empty prompt" in out["result"]
    assert state["requests"] == []


@pytest.mark.parametrize("orket_code,code,blocked", [
    ("E_MODEL_OUTPUT_LIMIT", "E_HOST_OUTPUT_LIMIT", True),
    ("E_MODEL_INPUT_BUDGET", "E_HOST_HTTP", False),
])
def test_an_output_ceiling_refusal_is_blocked_but_an_input_budget_is_not(
    host, tmp_path, orket_code, code, blocked
):
    """Orket 0.8.5+ refuses a request above the host's output ceiling. The same
    request goes to every repository, so it stops the batch; an input budget
    depends on the repository's size, so it fails only this one."""
    port, state = host
    state["status"] = 400
    message = f"{orket_code}: requested=1024, effective=768"
    state["detail"] = {"ok": False, "code": orket_code, "message": message}
    exit_code, out = _run(_clone(tmp_path), port)
    assert exit_code == 1 and out["is_error"] is True and out["blocked"] is blocked, out
    assert f"{code}:" in out["result"] and orket_code in out["result"]


def test_the_default_output_request_fits_every_packaged_orket_profile(host, tmp_path):
    """768 is the lowest packaged `concise_text` ceiling; 1024 was refused by
    most packaged profiles from Orket 0.8.5."""
    port, state = host
    exit_code, _out = _run(_clone(tmp_path), port)
    assert exit_code == 0
    assert state["requests"][-1][2]["max_tokens"] == 768


def test_a_target_clones_env_file_is_never_read(host, tmp_path):
    """gardener runs this command inside the target clone, so a repository's own
    .env must not be able to set the extension identity, host or credentials."""
    port, state = host
    repo = _clone(tmp_path)
    (repo / ".env").write_text("EXTENSION_ID=planted.namespace\n", encoding="utf-8")
    exit_code, out = _run(repo, port, drop=("EXTENSION_ID",))
    assert exit_code == 0, out
    assert state["requests"][0][0] == "/v1/extensions/stephenson.gardener-orket/runtime/llm/generate"
