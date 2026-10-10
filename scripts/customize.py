"""One-time identity setup after cloning; deliberately keeps Python module paths stable."""

import argparse
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def customize(root: Path, *, name: str, extension_id: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name):
        raise ValueError("Project name must be a lowercase hyphenated package name.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", extension_id):
        raise ValueError("Extension ID must be 1-128 letters, digits, dots, underscores or hyphens.")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    identity = re.search(
        r"^extension_id: ([A-Za-z0-9._-]+)$",
        (root / "extension.yaml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if identity is None:
        raise ValueError("Expected an unquoted extension_id in extension.yaml; no files changed.")
    old_id = identity.group(1)
    replacements = {
        "pyproject.toml": [(f'name = "{project["name"]}"', f'name = "{name}"')],
        "extension.yaml": [(f"extension_id: {old_id}", f"extension_id: {extension_id}")],
        "src/extension_template/__init__.py": [(old_id, extension_id)],
        ".env.example": [(f"EXTENSION_ID={old_id}", f"EXTENSION_ID={extension_id}")],
    }
    staged = {}
    for relative, pairs in replacements.items():
        path = root / relative
        content = path.read_text(encoding="utf-8")
        for old, new in pairs:
            if content.count(old) != 1:
                raise ValueError(f"Expected one template placeholder in {relative}; no files changed.")
            content = content.replace(old, new)
        staged[path] = content
    for path, content in staged.items():
        path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--extension-id", required=True)
    args = parser.parse_args()
    try:
        customize(ROOT, name=args.name, extension_id=args.extension_id)
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")
    print("Identity updated. Update README/product behavior, then install and validate.")
    print("Existing .env files are untouched; update EXTENSION_ID there if already configured.")


if __name__ == "__main__":
    main()
