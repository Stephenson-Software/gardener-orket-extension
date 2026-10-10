# Reference contract

Initial inspection: 2026-10-10. The following are provenance references, not dependencies:

- Companion at `dc4f6f0`: extension-owned orchestration in `api_client.py`, generic runtime
  transport in `host_runtime_client.py`, server-side host key, and local gateway separation.
- TextMystery at `b3b8f4e`: older product-specific integration and deterministic domain rules.
  It does not implement the same current generic BFF contract as Companion.
- Orket at `3ddc736f`: `orket/interfaces/routers/extension_runtime.py`, runtime service,
  public SDK contracts, and `docs/templates/external_extension` packaging guidance.

The Orket in-tree external template is Companion-shaped. This project is a separate headless
starter, with original neutral orchestration and adapters. It does not replace or modify the
in-tree template or either reference application.

SDK contracts used here are available in the installed 0.7.1 SDK and the inspected 0.8.0
source. Install an official SDK distribution explicitly; do not assume it is on public PyPI.
The Apache-2.0 license and Orket notice are retained from the in-tree starter. No Companion
UI, assets, configuration, or product behavior is copied.
