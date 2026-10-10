"""Integration proof over real sockets with a simulated host, not a live Orket/model."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def host_server():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("X-API-Key"), payload))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "ok": True,
                        "text": f"Simulated reply: {payload['user_message']}",
                        "model": "simulated-model",
                        "latency_ms": None,
                    }
                ).encode()
            )

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def env(tmp_path, port):
    values = {k: v for k, v in os.environ.items() if not k.startswith(("EXTENSION_", "ORKET_"))}
    values.update(
        {
            "EXTENSION_HOST_API_KEY": "host-secret",
            "EXTENSION_HOST_BASE_URL": f"http://127.0.0.1:{port}",
            "EXTENSION_ID": "example.test",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        }
    )
    return values


def test_cli_stdin_reaches_host_and_projects_json(host_server, tmp_path):
    port, requests = host_server
    result = subprocess.run(
        [sys.executable, "-m", "extension_template", "generate", "-"],
        cwd=tmp_path,
        env=env(tmp_path, port),
        input="hello",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "ok": True,
        "text": "Simulated reply: hello",
        "model": "simulated-model",
        "latency_ms": None,
    }
    assert result.stderr == ""
    assert len(requests) == 1
    assert requests[0][0] == "/v1/extensions/example.test/runtime/llm/generate"
    assert requests[0][1] == "host-secret"
    assert "host-secret" not in result.stdout


def test_cli_missing_key_and_invalid_input_are_nonzero(host_server, tmp_path):
    port, requests = host_server
    environment = env(tmp_path, port)
    environment.pop("EXTENSION_HOST_API_KEY")
    missing = subprocess.run(
        [sys.executable, "-m", "extension_template", "status"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert missing.returncode == 1 and missing.stdout == ""
    assert json.loads(missing.stderr)["error"]["code"] == "E_HOST_KEY_REQUIRED"
    invalid = subprocess.run(
        [sys.executable, "-m", "extension_template", "generate", " "],
        cwd=tmp_path,
        env=env(tmp_path, port),
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert invalid.returncode == 2 and invalid.stdout == ""
    assert json.loads(invalid.stderr)["error"]["code"] == "E_INPUT"
    assert requests == []


def test_cli_rejects_oversized_stdin_without_silently_truncating(host_server, tmp_path):
    port, requests = host_server
    result = subprocess.run(
        [sys.executable, "-m", "extension_template", "generate", "-"],
        cwd=tmp_path,
        env=env(tmp_path, port),
        input="x" * 16000 + " hidden-tail",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode != 0 and result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "E_INPUT"
    assert requests == []
