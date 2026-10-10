"""Bounded, read-only snapshot of a gardener target clone.

The model never receives file or shell tools. It receives this snapshot:
files the prompt names (only under the clone or gardener's ``add_dirs``), then
the repository's own docs, then its ``git ls-files`` listing, within byte
budgets. Each source gets a short opaque reference (``src01``) because a small
model has to echo the references it cites.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_PATH_PATTERN = re.compile(r"(?<![\w.-])(/[^\s`'\"()<>]+)")


@dataclass(frozen=True)
class SnapshotLimits:
    max_total_bytes: int = 24_000
    max_file_bytes: int = 6_000
    max_listed_files: int = 400
    docs: tuple[str, ...] = ("README.md", "CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md")


@dataclass(frozen=True)
class Source:
    ref: str
    path: str
    text: str


def collect_sources(prompt: str, repo: Path, roots: list[Path], limits: SnapshotLimits) -> list[Source]:
    repo = repo.resolve()
    allowed = [repo, *(root.resolve() for root in roots)]
    named = [Path(match.rstrip(".,:;")) for match in _PATH_PATTERN.findall(prompt)]
    candidates = [path for path in named if any(path.resolve().is_relative_to(root) for root in allowed)]
    candidates += [repo / name for name in limits.docs]
    sources: list[Source] = []
    used = 0
    for path in dict.fromkeys(candidate.resolve() for candidate in candidates):
        if used >= limits.max_total_bytes or not path.is_file():
            continue
        text = _read_head(path, min(limits.max_file_bytes, limits.max_total_bytes - used))
        if text is None:
            continue
        label = str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path)
        sources.append(Source(ref=f"src{len(sources) + 1:02d}", path=label, text=text))
        used += len(text.encode("utf-8"))
    sources.append(Source(ref="listing", path="git ls-files", text="\n".join(_tracked_files(repo, limits))))
    return sources


def _read_head(path: Path, limit: int) -> str | None:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    text = data[:limit].decode("utf-8", errors="replace")
    return text + ("\n[truncated]" if len(data) > limit else "")


def _tracked_files(repo: Path, limits: SnapshotLimits) -> list[str]:
    try:
        listing = subprocess.run(
            ["git", "ls-files"], cwd=repo, capture_output=True, text=True, timeout=60, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return ["[file listing unavailable]"]
    shown = listing[: limits.max_listed_files]
    hidden = len(listing) - len(shown)
    return shown + ([f"[{hidden} more not shown]"] if hidden > 0 else [])
