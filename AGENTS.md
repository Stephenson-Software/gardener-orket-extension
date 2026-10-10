# Extension contributor instructions

Read README.md and docs/architecture.md first. This repository is the starting point;
you do not need Companion, TextMystery, or a checkout of Orket to extend it.

- Keep the default workflow headless. Do not add a UI unless explicitly requested.
- Put product rules in `domain.py` and external orchestration in `service.py`.
- External host calls belong in `host_runtime.py`, through the generic
  `/v1/extensions/{extension_id}/runtime/*` contract. Never call model providers directly.
- A host-dispatched SDK workload uses `ctx.capabilities`; never call HTTP back into its host.
- Import public `orket_extension_sdk` contracts only. Never import `orket` internals.
- Keep secrets in process environment or ignored local env files. Do not emit them in logs,
  errors, output JSON, or checked-in examples. Do not forward raw upstream error bodies.
- Do not retry operations with potential side effects without defining idempotency first.
- The HTTP gateway is optional. Keep it a thin adapter to the same service as the CLI.
- Keep manifest ID, package default ID, and example environment in sync. Keep the package
  version and manifest version in sync. `scripts/customize.py` updates starter identity.
- Run `python scripts/validate.py` after behavior changes. For full adapter coverage install
  `[dev,gateway]`; without the gateway extra its tests are explicitly skipped.
- Report simulated-host tests separately from live Orket/model verification. Never substitute
  fake output after a host failure. Preserve unknown measurement values as null.
- Validate distributions with `python -m build`; the source distribution must include the
  manifest, source, tests, scripts, and docs. Do not publish or push without user direction.
