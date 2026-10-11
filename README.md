# gardener-orket-extension

Run [gardener](https://github.com/Stephenson-Software/gardener)'s report-only
repository audits through an [Orket](https://github.com/McElyea/Orket) host, on
whatever model that host serves.

This is a headless Orket extension built from
[McElyea/Orket-Extension-Template](https://github.com/McElyea/Orket-Extension-Template).
It needs no change to Orket.

## Which path to use

Orket 0.8.1+ ships its own governed Gardener harness,
[`examples/gardener_harness/`](https://github.com/McElyea/Orket/tree/main/examples/gardener_harness).
It runs each dispatch as a governed agent run:
- snapshots come from committed Git objects, from clean repositories only;
- the host's `structured_report.v1` verifier checks the report;
- final truth is recorded, and runs can be inspected and replayed.

Use it when you want that evidence and can serve a model through llama.cpp
or Ollama. Since Orket 0.8.2 it sets the model's context itself and its
limits are configurable; in testing, `qwen2.5:7b` delivered a useful report
through it.

This extension is the lighter alternative:
- one call to a running Orket host's generic runtime API;
- checks done here, not by Orket: report citations against the snapshot;
- no extension install into a project catalog, and no clean-repository
  requirement;
- no durable run record beyond gardener's own.

```text
gardener (command harness) -> orket-extension gardener -> ExtensionService.audit
    -> HostRuntimeClient -> Orket /v1/extensions/{id}/runtime/llm/generate -> host model
```

gardener chooses the work: which repository, which conventions, which prompt.
Since 0.3.0 it can hand a dispatch to a configured command instead of Claude
Code. `orket-extension gardener` is that command. It:

- builds a read-only snapshot of the target clone;
- asks the Orket host for one report;
- returns the report only if every citation in it refers to a source it was
  actually given;
- prints gardener's JSON envelope.

Scope: **report mode only**. `--implement`, `--file-issue`, `tend` and
`overnight` are refused before the host is called. The model never receives
file or shell tools, only text.

## How a dispatch runs

1. gardener starts `orket-extension gardener` in the target clone, with the
   prompt on stdin and `GARDENER_HARNESS_MODE` / `_SPEC` / `_MODEL` /
   `_TIMEOUT` in the environment.
2. The snapshot is built in this order, within byte budgets:
   - files the prompt names, only if they're under the clone or the spec's
     `add_dirs`;
   - the repository's own docs;
   - its `git ls-files` listing.

   Each source gets a short reference (`src01`, …, `listing`).
3. One `llm/generate` call goes to the host. The prompt asks for Markdown that
   cites a bracketed reference after each statement. The host selects the
   provider and calls the model.
4. `cited_sources` checks the reply:
   - a report citing nothing fails with `E_REPORT_UNSOURCED`;
   - a report citing a source it wasn't given fails with
     `E_REPORT_UNKNOWN_SOURCE`.

   Neither is passed on to gardener. Citations are checked; correctness is
   not. A report is model-assisted advice.
5. The report is returned with a footer naming the host, extension ID, model
   and cited sources.

The `gardener` command reads its settings from the **environment only**,
unless `--config-dir` is given. gardener runs it inside the target clone, so a
repository's own `.env` must never be able to choose the host, the
credentials or the extension ID.

## Set up

Prerequisites: Python 3.11+, the Orket SDK (wheel or source directory), and a
running Orket host.

```bash
python -m venv .venv && source .venv/bin/activate
python scripts/bootstrap.py --sdk "<path-to-orket-sdk-wheel-or-source>" --dev
orket-extension status   # with EXTENSION_HOST_API_KEY set; see .env.example
```

Start the host with its own launcher, for example
`ORKET_API_KEY=<key> ORKET_LLM_PROVIDER=ollama python server.py` from an Orket
checkout. It listens on `http://127.0.0.1:8082`.

## Configure gardener

In gardener's environment or `notify.env` (gardener 0.3.0+):

```bash
GARDENER_HARNESS=command
GARDENER_HARNESS_COMMAND="/path/to/.venv/bin/orket-extension gardener"
GARDENER_HARNESS_MODEL=qwen2.5-coder:32b      # optional; empty lets the host choose
EXTENSION_HOST_API_KEY=<the host's key>        # or ORKET_API_KEY
EXTENSION_HOST_BASE_URL=http://127.0.0.1:8082  # default
```

Optional settings, all read from the environment:

| Setting | Default | Meaning |
|---|---|---|
| `GARDENER_ORKET_PROVIDER` | host default | Provider requested from the host |
| `GARDENER_ORKET_MAX_TOKENS` | `1024` | Output tokens requested |
| `GARDENER_ORKET_REPORT_WORDS` | `250` | Report length asked of the model |
| `GARDENER_ORKET_MAX_TOTAL_BYTES` | `24000` | Snapshot text budget |
| `GARDENER_ORKET_MAX_FILE_BYTES` | `6000` | Per-file cap |
| `GARDENER_ORKET_MAX_FILES` | `400` | Listing entries |
| `GARDENER_ORKET_DOCS` | `README.md,CLAUDE.md,AGENTS.md,CONTRIBUTING.md,SECURITY.md` | Repository docs to include |
| `EXTENSION_TIMEOUT_SECONDS` | `GARDENER_HARNESS_TIMEOUT` | Host request timeout |

These are reported with `"blocked": true`, so a gardener overnight batch
stops instead of failing every repository the same way:
- an unreachable host, or rejected or missing credentials;
- a host server error (HTTP 5xx), which is how Orket 0.8.2 reports a model
  timeout on this API (McElyea/Orket#6);
- a request timeout.

Any other HTTP error fails only the current repository.

## Other commands

The template's `status`, `models`, `generate` and optional `serve` commands
are unchanged; see [docs/architecture.md](docs/architecture.md). The
template's SDK workload example (`extension.yaml`, `workload.py`) is also
unchanged. gardener uses the headless path, not host dispatch.

## Verify

```bash
python scripts/validate.py   # SDK manifest/import checks, ruff, tests
python -m build
```

The tests use real sockets with a simulated host. They do not exercise Orket
or a model. Live verification, including runs that refused or timed out with a
3B model, is recorded in [docs/verification.md](docs/verification.md).

## Limits

- **Snapshot only.** The model sees a bounded snapshot, not the repository,
  and can't check what it wasn't given.
- **The host's profile sets the limit (Orket 0.8.3+).** The host sizes the
  model's context from its prompt profile, and refuses a prompt that may not
  fit with HTTP 400 `E_MODEL_INPUT_BUDGET`, shown in the error. It uses a
  conservative byte-based estimate. With the packaged 8,192-token profile,
  gardener's own prompt plus the output budget already exceeds it, so every
  dispatch is refused. Start the host with a larger profile: point
  `ORKET_LOCAL_PROMPT_PROFILE_REGISTRY_PATH` at a copy of Orket's
  `orket/runtime/config/local_prompt_profiles.json` whose profile for your
  model has a larger `context_budget_tokens` (32,768 worked in testing).
  - **Before 0.8.3:** the API did not set the context at all, so a prompt
    longer than the server's context was silently dropped
    (McElyea/Orket#6).
- **Unsupported content is refused.** Orket's typed refusals reach gardener
  with their code. A host timeout or an unavailable model (HTTP 504/503 on
  0.8.4) is reported as `blocked`.
- **Small models.** With a small local model, keep the snapshot small. The
  observed run used `GARDENER_ORKET_MAX_TOTAL_BYTES=8000` with `llama3.2:3b`.
  Expect a checklist that is often wrong.
- **Format only.** Citations are checked for existence and provenance, not for
  whether the cited source supports the statement.
