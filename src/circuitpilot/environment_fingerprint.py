"""Strict software, operating-system, Git, and ngspice provenance capture."""

from __future__ import annotations

from hashlib import sha256
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
from typing import Any
from urllib.parse import unquote, urlparse

from circuitpilot.exceptions import ResearchArtifactError
from circuitpilot.simulator import resolve_ngspice_executable


RESEARCH_BASELINE_VERSION = "v0.5-research-baseline"
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _distribution_version(name: str) -> str:
    """Return an installed distribution version or fail provenance capture."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError as exc:
        raise ResearchArtifactError(
            f"cannot fingerprint required Python distribution '{name}'"
        ) from exc


def _direct_url_checkout() -> Path | None:
    """Locate a source checkout recorded by pip's PEP 610 metadata."""
    try:
        direct_url = metadata.distribution("circuitpilot").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not direct_url:
        return None
    try:
        url = json.loads(direct_url).get("url")
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    raw_path = unquote(parsed.path)
    if os.name == "nt" and raw_path.startswith("/") and len(raw_path) > 2:
        raw_path = raw_path[1:]
    candidate = Path(raw_path)
    return candidate if candidate.is_dir() else None


def _git_commit() -> tuple[str, bool | None]:
    """Resolve the exact Git commit and dirty state or fail explicitly."""
    override = os.environ.get("CIRCUITPILOT_GIT_COMMIT", "").strip().lower()
    if override:
        if _COMMIT_PATTERN.fullmatch(override) is None:
            raise ResearchArtifactError(
                "CIRCUITPILOT_GIT_COMMIT must be a 40-character hexadecimal SHA"
            )
        dirty_override = os.environ.get("CIRCUITPILOT_GIT_DIRTY")
        dirty = None if dirty_override is None else dirty_override == "1"
        return override, dirty

    candidates: list[Path] = []
    direct_url_checkout = _direct_url_checkout()
    if direct_url_checkout is not None:
        candidates.append(direct_url_checkout)
    candidates.extend((Path(__file__).resolve().parents[2], Path.cwd()))
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        pyproject = resolved / "pyproject.toml"
        try:
            if (
                not pyproject.is_file()
                or 'name = "circuitpilot"' not in pyproject.read_text(encoding="utf-8")
            ):
                continue
        except (OSError, UnicodeError):
            continue
        try:
            commit_process = subprocess.run(
                ["git", "-C", str(resolved), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        commit = commit_process.stdout.strip().lower()
        if commit_process.returncode != 0 or _COMMIT_PATTERN.fullmatch(commit) is None:
            continue
        dirty: bool | None = None
        try:
            status_process = subprocess.run(
                ["git", "-C", str(resolved), "status", "--porcelain"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10.0,
                check=False,
            )
            if status_process.returncode == 0:
                dirty = bool(status_process.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
        return commit, dirty
    raise ResearchArtifactError(
        "cannot determine Git commit; run from a checkout or set "
        "CIRCUITPILOT_GIT_COMMIT to the exact source commit"
    )


def _hash_file(path: Path) -> str:
    """Stream one binary file into SHA-256 without loading it all at once."""
    digest = sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ResearchArtifactError(
            f"failed to hash ngspice executable '{path}': {exc}"
        ) from exc
    return digest.hexdigest()


def _ngspice_version(executable: Path) -> str:
    """Execute ngspice's version command and return its identifying line."""
    try:
        completed = subprocess.run(
            [str(executable), "-v"],
            cwd=executable.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15.0,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResearchArtifactError("ngspice version query timed out") from exc
    except OSError as exc:
        raise ResearchArtifactError(f"failed to query ngspice version: {exc}") from exc
    if completed.returncode != 0:
        raise ResearchArtifactError(
            f"ngspice version query exited with status {completed.returncode}"
        )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    for line in combined.splitlines():
        if "ngspice-" in line.lower():
            return line.strip().strip("*").strip()
    raise ResearchArtifactError("ngspice version query returned no version string")


def collect_environment_fingerprint(ngspice_executable: str) -> dict[str, Any]:
    """Collect the complete environment fingerprint required by the baseline."""
    resolved = resolve_ngspice_executable(ngspice_executable)
    if resolved is None:
        raise ResearchArtifactError(
            f"ngspice executable '{ngspice_executable}' cannot be resolved for provenance"
        )
    executable_path = Path(resolved).resolve()
    commit, dirty = _git_commit()
    return {
        "git_commit_hash": commit,
        "git_worktree_dirty": dirty,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "os_information": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "numpy_version": _distribution_version("numpy"),
        "scipy_version": _distribution_version("scipy"),
        "optuna_version": _distribution_version("optuna"),
        "pyyaml_version": _distribution_version("PyYAML"),
        "ngspice_version_string": _ngspice_version(executable_path),
        "ngspice_executable_path": str(executable_path),
        "ngspice_executable_sha256": _hash_file(executable_path),
        "circuitpilot_version": _distribution_version("circuitpilot"),
        "research_baseline_version": RESEARCH_BASELINE_VERSION,
    }
