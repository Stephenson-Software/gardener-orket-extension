"""Install into the active Python environment. SDK distribution is an explicit input."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", default=os.getenv("ORKET_SDK_INSTALL_SPEC", ""))
    parser.add_argument("--gateway", action="store_true")
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.sdk:
        subprocess.run([sys.executable, "-m", "pip", "install", args.sdk], check=True)
    else:
        try:
            import orket_extension_sdk  # noqa: F401
        except ImportError:
            parser.error("Supply --sdk <wheel-or-source-path> or install the official SDK first.")
    extras = [name for name in ("dev", "gateway") if getattr(args, name)]
    target = str(root) + (f"[{','.join(extras)}]" if extras else "")
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", target], check=True)


if __name__ == "__main__":
    main()
