# Verification record

Real runs of `orket-extension gardener` through a live Orket host, 2026-10-10.
The tests in `tests/` use a simulated host and are not repeated here.

## Environment

- **Machine:** WSL2 (Linux 5.10), Python 3.11.15, GeForce GT 1030 (2 GB).
- **gardener:** v0.3.0 (released tag), `GARDENER_HARNESS=command`.
- **Orket host:** `python server.py` from an Orket checkout at `f7136ac`, which
  is 0.8.0 plus PR #2. Only the generic `/v1/extensions/{id}/runtime/*` API is
  used, which is unchanged since 0.8.0. Started with `ORKET_LLM_PROVIDER=ollama`
  and a local throwaway API key.
- **Model:** Ollama 0.24.0, `llama3.2:3b`, server-default 4096-token context.
- **Target:** the public `Stephenson-Software/multiplyTwoNumbers` clone.
- **Isolation:** each run had its own isolated gardener state and cache
  directory. Snapshot settings were `GARDENER_ORKET_MAX_TOTAL_BYTES=8000` and
  `GARDENER_ORKET_MAX_FILE_BYTES=3000`.

## Results

| When (UTC) | Conventions | Outcome |
|---|---|---|
| 18:59 | operator's real conventions repo | **Delivered.** gardener exit 0 in 104.5 s. The report cited `src03` and `listing`, both supplied, and both were checked. Clone `git status --porcelain` empty; GitHub `pushedAt` unchanged |
| 19:3x | minimal three-item conventions repo | **Refused**, as designed. The model cited no sources, giving `E_REPORT_UNSOURCED` and gardener exit 1 |
| 19:4x | operator's real conventions repo | **Timed out** after gardener's 900 s. The host logged `ModelTimeoutError: llama3.2:3b timed out after 3 attempts`. By then Ollama was running the model mostly on CPU, after an earlier stuck runner had been stopped |

Every run left the clone clean, and GitHub `pushedAt` stayed
`2026-09-04T02:27:40Z` throughout.

The delivered run's code is identical to `8b50240` in `src/`. Only tests and
docs changed afterwards.

## Reading the results

- **The plumbing works.** The path gardener → this extension → Orket runtime
  API → host-selected model works end to end.
- **The citation rule works.** It refuses unsourced output instead of passing
  it on.
- **A 3B model is not enough.** It cites inconsistently, and on this hardware
  it can exceed the host's per-call model timeout. The one delivered report
  was largely wrong. Use a larger model on a host that can serve it before
  relying on the output.

## Orket's own harness, for comparison

The same day, Orket 0.8.1 merged its own governed Gardener harness
(`examples/gardener_harness/`, McElyea/Orket@`ebe00ca`). It was run once each
on this machine:

| Conventions | Outcome |
|---|---|
| Operator's real conventions repo (~92 KB of docs) | Refused before the model ran: "selected snapshot content exceeds the byte budget" (64 KiB). This is its documented limit |
| Minimal conventions repo | Refused by its `structured_report.v1` verifier. Each call was charged exactly 4,096 input tokens: Ollama's default context truncated the prompt, and the model echoed the verifier configuration instead of a report. Its default provider is llama.cpp, which was not available here |
