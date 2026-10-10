import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .domain import GenerateInput
from .errors import ExtensionError
from .host_runtime import HostRuntimeClient
from .service import ExtensionService
from .settings import load_settings


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Headless Orket extension. Results are JSON on stdout.")
    root.add_argument(
        "--config-dir", type=Path, default=Path.cwd(), help="Directory containing .env/.env.local"
    )
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Inspect host runtime availability")
    models = commands.add_parser("models", help="List models through the host")
    models.add_argument("--provider", default="")
    generate = commands.add_parser("generate", help="Run the example; use '-' to read a message from stdin")
    generate.add_argument("message")
    generate.add_argument("--provider", default="")
    generate.add_argument("--model", default="")
    generate.add_argument("--max-tokens", type=int, default=512)
    generate.add_argument("--temperature", type=float, default=0.2)
    serve = commands.add_parser("serve", help="Start the optional local HTTP adapter (requires [gateway])")
    serve.add_argument("--port", type=int, choices=range(1, 65536), metavar="PORT", default=3001)
    return root


async def execute(args: argparse.Namespace, settings) -> dict:
    async with HostRuntimeClient(settings) as host:
        if args.command == "status":
            return await host.status()
        if args.command == "models":
            return await host.models(provider=args.provider)
        request = GenerateInput(
            message=args.message,
            provider=args.provider,
            model=args.model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        return await ExtensionService(host).generate(request)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = load_settings(args.config_dir)
        if args.command == "serve":
            try:
                import uvicorn

                from .gateway import create_app
            except ImportError as exc:
                raise ExtensionError(
                    "E_GATEWAY_INSTALL", "Install the [gateway] extra to serve HTTP."
                ) from exc
            uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, proxy_headers=False)
            return 0
        if args.command == "generate" and args.message == "-":
            # Bound input before validation; avoid loading an unbounded pipeline into memory.
            args.message = sys.stdin.read(16001)
            if len(args.message) > 16000:
                raise ExtensionError("E_INPUT", "Standard input exceeds 16000 characters.", status=422)
        payload = asyncio.run(execute(args, settings))
    except ValidationError:
        payload = ExtensionError(
            "E_INPUT", "Invalid generation input. See --help for limits.", status=422
        ).as_dict()
        print(json.dumps(payload), file=sys.stderr)
        return 2
    except ExtensionError as exc:
        print(json.dumps(exc.as_dict()), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    # ASCII escapes keep JSON portable through Windows consoles and automation pipes.
    print(json.dumps(payload))
    return 0
