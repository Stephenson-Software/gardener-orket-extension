"""Portable contributor checks; does not claim a live host or model was exercised."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    checks = [
        ["orket_extension_sdk.validate", ".", "--strict", "--json"],
        ["orket_extension_sdk.import_scan", "src", "--json"],
        ["ruff", "check", "."],
        ["pytest", "-q"],
    ]
    for check in checks:
        subprocess.run([sys.executable, "-m", *check], cwd=root, check=True)


if __name__ == "__main__":
    main()
