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

Note (2026-10-16): that held when it was written. `src/` has changed since,
and the rechecks below ran later code.

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

## Orket 0.8.2 recheck (2026-10-11)

Run through gardener's integration suite
([INTEGRATION_TESTS.md](https://github.com/Stephenson-Software/gardener/blob/main/docs/INTEGRATION_TESTS.md)),
with the host restarted on Orket `v0.8.2` (`555685f9`). Same machine,
CPU-only Ollama, server context 16,384.

| Run | Outcome |
|---|---|
| Command tier, bundled fixture conventions, `llama3.2:3b` | **Delivered**, and `--implement` refused by the extension. Both tests passed in 90 s |
| Real conventions, `llama3.2:3b`, 8 KB snapshot | Refused by the citation check: `E_REPORT_UNSOURCED` (178 s) |
| Real conventions, `qwen2.5:7b`, 8 KB snapshot | The host's per-call model timeout (about 300 s) came back as a bare HTTP 500 (303 s), with no retry |

Every run left the target clone clean, and its GitHub `pushedAt` stayed
`2026-09-04T02:27:40Z`.

A probe of the host's `llm/generate` API found that a message over the
server's context is dropped: an 83 KB message reached the model as 19 input
tokens, and the host returned `ok: true`. This was filed as McElyea/Orket#6.
This extension's default snapshot budget stays far below that limit.

Since this recheck, a host server error or timeout is reported as
`"blocked": true`, so a gardener batch stops on it.

## Orket 0.8.4 recheck (2026-10-11)

The host ran Orket `v0.8.4` (`048e7468`) on the same machine, with Ollama
back on its default settings.

| Probe or run | Outcome |
|---|---|
| `llm/generate`, 664-character message | answered correctly (202 input tokens) |
| `llm/generate`, 16.5 KB and 83 KB messages | HTTP 400 `E_MODEL_INPUT_BUDGET`, before generation: no longer silently dropped (#6 fixed) |
| `orket-extension gardener`, host on the default 8,192-token profile, any snapshot size (3 KB, 8 KB, 24 KB) | refused with HTTP 400 `E_MODEL_INPUT_BUDGET`: gardener's prompt and the output budget exceed the profile |
| The same, host started with a 32,768-token profile | reached the model, with 8 KB (77 s) and 24 KB (143 s) snapshots. `llama3.2:3b` cited no source, and the citation check refused both (`E_REPORT_UNSOURCED`) |

Since this recheck:
- the extension passes on Orket's typed error code, and the message too when
  it is plain (see `host_runtime._http_failure`);
- the README says how to raise the host's profile.

The model is still the limiting factor: on 0.8.4, `qwen2.5:7b` delivered
through Orket's own governed harness, but `llama3.2:3b` did not deliver on
either path.

## Orket 0.8.8 recheck (2026-10-11)

The host ran Orket `v0.8.8` (`631444b5`) on the same machine, Ollama on its
default settings, `qwen2.5:7b`. Each run went through gardener's real
`align` prompt, using gardener's integration sandbox.

| Host profile | Request | Outcome |
|---|---|---|
| packaged 8,192 tokens | 1,024 output tokens (the old default) | HTTP 400 `E_MODEL_OUTPUT_LIMIT: requested=1024, effective=768`, in 0.4 s. The qwen profile's ceiling on this API is 768. The 0.8.4 recheck used `llama3.2:3b`, whose profile allows 1,536, so it did not show then |
| packaged 8,192 tokens | 768 output tokens | HTTP 400 `E_MODEL_INPUT_BUDGET: utf8_byte_estimate=7538, input_limit=8192 ...`. The message now names `ORKET_LOCAL_PROMPT_PROFILE_REGISTRY_PATH` (0.8.6) and says the input was not truncated |
| 32,768 tokens | 768 output tokens | reached the model (70 s). `qwen2.5:7b` cited no source, so the citation check refused it (`E_REPORT_UNSOURCED`) |

Since this recheck:
- the default request is 768 tokens;
- an output-ceiling refusal is reported as `blocked` (`E_HOST_OUTPUT_LIMIT`),
  confirmed against the live 0.8.8 host with a 1,024-token request.

The model is still the limit on this path: neither `llama3.2:3b` nor
`qwen2.5:7b` has produced a cited report through the extension on this
machine. `qwen2.5:7b` does deliver through Orket's own governed harness; see
gardener's `docs/verification/orket-0.8.8.md`.
