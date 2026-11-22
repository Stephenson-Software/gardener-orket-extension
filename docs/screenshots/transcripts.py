"""Run the real `orket-extension gardener` command against a simulated host and
write each terminal session as an HTML page for darkroom to photograph.

The host here is the same kind of stand-in the test suite uses
(tests/test_gardener_cli.py): it answers Orket's
`/v1/extensions/{id}/runtime/llm/generate` with a canned reply. Nothing is sent
to Orket or to a model. Everything shown on the pages is the command's actual
stdout and exit code.

Usage: python docs/screenshots/transcripts.py <out-dir>  (from an environment with the
package installed, so the command shows its own name)
"""

import html
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT = "Audit this repository's documentation and list the gaps a new contributor would hit."
GOOD_REPLY = (
    "## Documentation gaps\n\n"
    "- The README names no test command, so a contributor cannot tell how to check a change [src01].\n"
    "- No tests/ directory or CONTRIBUTING.md appears among the tracked files [listing].\n"
    "- `src/inventory/cli.py` is tracked, but the README shows no usage example for it [src01] [listing]."
)
BAD_REPLY = "Tests are run with `make check` [src01], configured in the Makefile [src07]."


def start_host(state):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps({"ok": True, "text": state["reply"], "model": "simulated-model",
                               "latency_ms": None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def demo_clone(base: Path) -> Path:
    repo = base / "inventory-demo"
    (repo / "src" / "inventory").mkdir(parents=True)
    (repo / "README.md").write_text("# inventory-demo\n\nTrack stock levels from the command line.\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "inventory-demo"\nrequires-python = ">=3.11"\n')
    (repo / "src" / "inventory" / "__init__.py").write_text("")
    (repo / "src" / "inventory" / "cli.py").write_text("def main():\n    print('inventory')\n")
    for argv in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)
    return repo


def run(repo: Path, port: int, args, *, mode="report", prompt=PROMPT):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EXTENSION_", "ORKET_", "GARDENER_"))}
    env.update({
        "EXTENSION_HOST_API_KEY": "demo-key", "EXTENSION_HOST_BASE_URL": f"http://127.0.0.1:{port}",
        "PYTHONPATH": str(ROOT / "src"), "GARDENER_HARNESS_MODE": mode,
        "GARDENER_HARNESS_MODEL": "qwen2.5-coder:32b",
        "GARDENER_HARNESS_SPEC": json.dumps({"mode": mode, "add_dirs": []}), "GARDENER_HARNESS_TIMEOUT": "60",
    })
    script = Path(sys.executable).with_name("orket-extension")
    argv = [str(script)] if script.exists() else [sys.executable, "-m", "extension_template"]
    proc = subprocess.run([*argv, *args], cwd=repo, env=env,
                          input=prompt, text=True, capture_output=True, timeout=60)
    return proc.returncode, proc.stdout


def colour(text: str) -> str:
    out = html.escape(text)
    out = re.sub(r'^(\s*)(&quot;[a-z_]+&quot;)(:)', r'\1<span class="k">\2</span>\3', out, flags=re.M)
    out = re.sub(r"(E_[A-Z_]+)", r'<span class="e">\1</span>', out)
    out = re.sub(r"(\[(?:src\d\d|listing)\])", r'<span class="c">\1</span>', out)
    return out


def page(title: str, blocks) -> str:
    body = []
    for cmd, output, code in blocks:
        body.append(f'<div class="cmd"><span class="p">$</span> {html.escape(cmd)}</div>')
        if output:
            body.append(f"<pre>{colour(output.rstrip())}</pre>")
        if code is not None:
            cls = "ok" if code == 0 else "bad"
            body.append(f'<div class="exit {cls}">exit {code}</div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ margin: 0; background: #0d1117; font: 14px/1.45 "DejaVu Sans Mono", monospace; color: #c9d1d9; }}
.term {{ margin: 24px; border: 1px solid #30363d; border-radius: 8px; background: #161b22;
  max-width: 1180px; }}
.bar {{ padding: 8px 14px; border-bottom: 1px solid #30363d; color: #8b949e; font-size: 12px; }}
.bar i {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px;
  background: #30363d; }}
.inner {{ padding: 14px 18px 18px; }}
.cmd {{ color: #e6edf3; white-space: pre-wrap; margin-top: 10px; }}
.cmd:first-child {{ margin-top: 0; }}
.p {{ color: #3fb950; }}
pre {{ margin: 6px 0 0; white-space: pre-wrap; word-break: break-word; font: inherit; }}
.k {{ color: #79c0ff; }} .e {{ color: #ff7b72; font-weight: bold; }} .c {{ color: #d2a8ff; }}
.exit {{ margin-top: 4px; font-size: 12px; }} .ok {{ color: #3fb950; }} .bad {{ color: #f0883e; }}
</style></head><body><div class="term"><div class="bar"><i></i><i></i><i></i>{html.escape(title)}</div>
<div class="inner">{''.join(body)}</div></div></body></html>
"""


def main() -> None:
    out_dir = Path(sys.argv[1]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    state = {"reply": GOOD_REPLY}
    server = start_host(state)
    port = server.server_port
    shown_cmd = "orket-extension gardener < prompt.txt > envelope.json"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            repo = demo_clone(Path(tmp))

            code, help_text = run(repo, port, ["--help"])
            (out_dir / "help.html").write_text(page("orket-extension --help", [
                ("orket-extension --help", help_text, None)]))

            code, stdout = run(repo, port, ["gardener"])
            env = json.loads(stdout)
            rest = json.dumps({k: v for k, v in env.items() if k != "result"}, indent=2)
            (out_dir / "report.html").write_text(page("A cited report is returned (simulated host)", [
                ("cat prompt.txt", PROMPT, None),
                (shown_cmd, "", code),
                ("jq -r .result envelope.json", env["result"], None),
                ("jq 'del(.result)' envelope.json", rest, None),
            ]))

            state["reply"] = BAD_REPLY
            code_bad, bad = run(repo, port, ["gardener"])
            code_mode, mode_out = run(repo, port, ["gardener"], mode="implement")
            server.shutdown()
            server.server_close()
            server = None
            code_down, down = run(repo, port, ["gardener"])
            pretty = lambda s: json.dumps(json.loads(s), indent=2)  # noqa: E731
            (out_dir / "refusals.html").write_text(page("Refused and blocked dispatches (simulated host)", [
                ("# the model cites [src07], a source it was never given", "", None),
                ("orket-extension gardener < prompt.txt", pretty(bad), code_bad),
                ("# gardener asks for implement mode", "", None),
                ("GARDENER_HARNESS_MODE=implement orket-extension gardener < prompt.txt",
                 pretty(mode_out), code_mode),
                ("# the Orket host is not running", "", None),
                ("orket-extension gardener < prompt.txt", pretty(down), code_down),
            ]))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
    print("wrote", ", ".join(sorted(p.name for p in out_dir.glob("*.html"))))


if __name__ == "__main__":
    main()
