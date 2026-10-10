import runpy
import shutil
import tomllib
from pathlib import Path

import pytest
from orket_extension_sdk.manifest import load_manifest
from orket_extension_sdk.validate import validate_extension

from extension_template import DEFAULT_EXTENSION_ID

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.contract


def test_manifest_and_packaging_identity_agree():
    manifest = load_manifest(ROOT / "extension.yaml")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert manifest.extension_id == DEFAULT_EXTENSION_ID
    assert manifest.extension_version == project["version"]
    assert f"EXTENSION_ID={DEFAULT_EXTENSION_ID}" in (ROOT / ".env.example").read_text()
    assert validate_extension(ROOT)["ok"]


def test_customization_updates_clone_without_changing_module_paths(tmp_path):
    for relative in [
        "pyproject.toml",
        "extension.yaml",
        ".env.example",
        "src/extension_template/__init__.py",
    ]:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    customize = runpy.run_path(str(ROOT / "scripts/customize.py"))["customize"]
    customize(tmp_path, name="my-extension", extension_id="example.my-extension")
    manifest = load_manifest(tmp_path / "extension.yaml")
    assert manifest.extension_id == "example.my-extension"
    assert manifest.workloads[0].entrypoint == "extension_template.workload:run"
    assert 'name = "my-extension"' in (tmp_path / "pyproject.toml").read_text()
    assert (
        'DEFAULT_EXTENSION_ID = "example.my-extension"'
        in (tmp_path / "src/extension_template/__init__.py").read_text()
    )
    before = (tmp_path / "pyproject.toml").read_text()
    # A partially hand-edited identity must fail preflight without changing other files.
    (tmp_path / ".env.example").write_text("EXTENSION_ID=unrelated.id\n")
    with pytest.raises(ValueError, match="placeholder"):
        customize(tmp_path, name="another", extension_id="example.another")
    assert (tmp_path / "pyproject.toml").read_text() == before
