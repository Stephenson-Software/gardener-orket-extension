# Orket-Extension-Template

A headless starting point for Orket extensions. Clone it, set your extension identity,
and replace the example behavior. The host communication plumbing is already here.

```text
CLI / Python automation -> ExtensionService -> HostRuntimeClient -> Orket runtime
Optional HTTP caller   -> local gateway ---^

Orket workload runner  -> workload.run(ctx, payload) -> injected SDK capabilities
```

The first path captures Companion's extension-owned orchestration boundary without its UI
or product logic. The second is the SDK workload entrypoint used when Orket itself dispatches
work. These are separate entry modes. Calling the runtime API does not execute `workload.run`.

## Start a new extension

Prerequisites: Python 3.11+, an official Orket SDK wheel or SDK source directory, and an
Orket host for live calls. The SDK can also be preinstalled in the chosen environment.
No Node, browser, frontend build, or Orket host package is needed in the extension environment.

Select **Use this template** on
[GitHub](https://github.com/McElyea/Orket-Extension-Template) to create your own repository,
then clone it. To clone this starter directly instead:

```powershell
git clone https://github.com/McElyea/Orket-Extension-Template.git my-extension
cd my-extension
```

From your new project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python scripts/customize.py --name my-extension --extension-id example.my-extension
python scripts/bootstrap.py --sdk "<path-to-official-sdk-wheel-or-source>" --dev
Copy-Item .env.example .env.local
```

On Unix, activate with `source .venv/bin/activate` and copy with `cp .env.example .env.local`;
the Python commands are identical. If the SDK is already installed, omit `--sdk`.
`ORKET_SDK_INSTALL_SPEC` is an alternative to that argument. Bootstrap uses the active
Python environment and does not install or start the Orket host.

Set `EXTENSION_HOST_API_KEY` in `.env.local` to the key configured on your host, or supply
`ORKET_API_KEY` in the process environment. Start your Orket host using its own documented
launcher. The template defaults to `http://127.0.0.1:8082`; override
`EXTENSION_HOST_BASE_URL` if yours differs.

```powershell
orket-extension status
orket-extension models
orket-extension generate "Describe the task this extension will perform."
"Summarize this input." | orket-extension generate -
```

`python -m extension_template` is equivalent to `orket-extension`. Successful data commands
write JSON to stdout; data/runtime failures write safe JSON to stderr and exit nonzero
(argument syntax errors use standard CLI help). `status` reports
capability availability; a successful status call does not imply an available model. No
sample response or silent provider fallback is supplied by the template.

`--provider` and `--model` may be supplied to `generate` when supported by your host. Leaving
them empty delegates selection to Orket. Env files are read from the current directory;
use `orket-extension --config-dir <directory> status` when running elsewhere. Shell values
override `.env.local`, which overrides `.env`. Values are literal; env interpolation is disabled.

## What to change

| Location | Responsibility |
| --- | --- |
| `src/extension_template/domain.py` | Product input schema, prompt, deterministic rules |
| `src/extension_template/service.py` | Product orchestration using the host adapter |
| `src/extension_template/host_runtime.py` | Model, memory, voice and TTS HTTP plumbing |
| `src/extension_template/cli.py` | Headless command interface |
| `src/extension_template/workload.py` | Host-dispatched SDK capability example |
| `src/extension_template/gateway.py` | Optional authenticated HTTP adapter |
| `extension.yaml` | Extension identity, workload entrypoints and required capabilities |

The example generates one response and is intentionally stateless. Add memory explicitly
in the service when your product needs it. [Architecture and recipes](docs/architecture.md)
explain memory namespaces, authority boundaries, error behavior, and both entry modes.

Customization updates the distribution name, manifest ID, runtime default ID, and `.env.example`.
It preserves the neutral Python module and `orket-extension` command to avoid mass renames.
Use separate virtual environments for different clones. Update existing local env files yourself.
Edit README/product behavior for your new extension. Keep package and manifest versions aligned.

## Optional HTTP adapter

Only needed when another local process wants an HTTP endpoint. There is no UI.

```powershell
python -m pip install -e ".[gateway]"
# Set EXTENSION_GATEWAY_TOKEN in .env.local to a distinct random secret, at least 32 characters.
orket-extension serve --port 3001
```

Calls require `Authorization: Bearer <gateway-token>`. Available routes are
`GET /api/status`, `GET /api/models?provider=...`, and `POST /api/generate` with a JSON body
such as `{"message":"Hello"}`. This token is separate from the upstream host key.
The launcher binds only to loopback, disables proxy-header trust, checks caller addresses,
and bounds bodies to 64 KiB before decoding. It exposes no generic forwarding endpoint.
Remote deployment needs a separately designed authentication and transport policy.

## Verify and package

```powershell
python -m pip install -e ".[dev,gateway]"
python scripts/validate.py
python -m build
```

Validation runs SDK manifest/import checks, lint, and tests. Tests include actual local HTTP
with a simulated host; they do not require Orket or a model service. The optional gateway
tests are skipped when its dependencies are absent. For live proof, run the status/models/
generate commands above against your real host and inspect the returned capability flags/output.

The wheel supports installed CLI/library/gateway usage. The source distribution also carries
the root manifest, tests, docs, and scripts for host admission and further development. From
an environment with the Orket CLI, use `orket ext validate <source-root> --strict --json` for
host-side admission checking. Validation does not register an extension or grant runtime authority.

See [provenance](docs/provenance.md) for the local reference revisions used to establish the
contract. The template does not depend on either reference project.
