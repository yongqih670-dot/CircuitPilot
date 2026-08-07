"""Install CircuitPilot in a new virtual environment and run real ngspice E2E."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Sequence


RESEARCH_LOCK_FILENAME = "requirements-research.lock"


def _run_checked(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one external command, print captured output, and require success."""
    printable = subprocess.list2cmdline(list(command))
    print(f"$ {printable}", flush=True)
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command exited with status {completed.returncode}: {printable}"
        )
    return completed


def _resolve_ngspice(project_root: Path, requested: str) -> Path:
    """Resolve ngspice without importing CircuitPilot from the source checkout."""
    explicit = Path(requested)
    if explicit.is_file():
        return explicit.resolve()
    on_path = shutil.which(requested)
    if on_path is not None:
        resolved = Path(on_path).resolve()
        if resolved.name.lower() == "ngspice.exe":
            console = resolved.with_name("ngspice_con.exe")
            if console.is_file():
                return console
        return resolved
    if requested == "ngspice":
        local = project_root / "tools" / "ngspice" / "bin" / "ngspice_con.exe"
        if local.is_file():
            return local.resolve()
    raise RuntimeError(
        f"ngspice executable '{requested}' was not found; clean test cannot continue"
    )


def _git_source_identity(project_root: Path) -> tuple[str, bool]:
    """Return the checkout commit and dirty state passed into the clean wheel run."""
    commit = _run_checked(
        ["git", "-C", str(project_root), "rev-parse", "HEAD"],
        cwd=project_root,
    ).stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise RuntimeError("git rev-parse did not return a full hexadecimal commit")
    status = _run_checked(
        ["git", "-C", str(project_root), "status", "--porcelain"],
        cwd=project_root,
    ).stdout
    return commit, bool(status.strip())


def _venv_python(venv_directory: Path) -> Path:
    """Return the platform-specific Python executable in a virtual environment."""
    if os.name == "nt":
        return venv_directory / "Scripts" / "python.exe"
    return venv_directory / "bin" / "python"


def _write_clean_optimization_config(path: Path) -> None:
    """Write a small deterministic optimization used by the clean smoke test."""
    path.write_text(
        """circuit:
  type: rc_lowpass
objective:
  metric: bandwidth
  goal: target
  target_value: 1000
parameters:
  R: {min: 900, max: 1100, scale: log}
  C: {min: 140e-9, max: 180e-9, scale: log}
optimizer:
  max_iterations: 1
  population_size: 2
  tolerance: 0.01
  seed: 20260801
  polish: false
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 100000
  points_per_decade: 50
""",
        encoding="utf-8",
    )


def _verify_artifacts(run_directory: Path, expected_git_commit: str) -> None:
    """Cross-check clean-run manifest, raw output, history, and SQLite record."""
    required = (
        "research_manifest.json",
        "input_config.yaml",
        "optimization_history.csv",
        "optimization_summary.json",
        "optimization_progress.png",
        "experiments.sqlite3",
        "run_context.json",
    )
    missing = [name for name in required if not (run_directory / name).is_file()]
    if missing:
        raise RuntimeError(f"clean run is missing artifact(s): {', '.join(missing)}")
    manifest = json.loads(
        (run_directory / "research_manifest.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (run_directory / "optimization_summary.json").read_text(encoding="utf-8")
    )
    if manifest["reproducibility"]["random_seed"] != 20260801:
        raise RuntimeError("clean manifest did not preserve the configured random seed")
    if manifest["reproducibility"]["metric_source"] != "parsed_ngspice_output":
        raise RuntimeError("clean manifest metric provenance is not ngspice")
    environment = manifest["environment"]
    required_fingerprint = {
        "git_commit_hash",
        "python_version",
        "os_information",
        "numpy_version",
        "scipy_version",
        "optuna_version",
        "pyyaml_version",
        "ngspice_version_string",
        "ngspice_executable_sha256",
        "circuitpilot_version",
    }
    missing_fingerprint = sorted(required_fingerprint - set(environment))
    if missing_fingerprint:
        raise RuntimeError(
            "clean manifest is missing fingerprint field(s): "
            + ", ".join(missing_fingerprint)
        )
    if len(environment["ngspice_executable_sha256"]) != 64:
        raise RuntimeError("clean manifest contains an invalid ngspice SHA-256")
    if environment["git_commit_hash"] != expected_git_commit:
        raise RuntimeError("clean manifest Git commit does not match installed source")
    if environment["research_baseline_version"] != "v0.5-research-baseline":
        raise RuntimeError("clean manifest does not identify the frozen research baseline")
    if manifest["run"]["run_id"] not in (run_directory / "run_context.json").read_text(
        encoding="utf-8"
    ):
        raise RuntimeError("clean manifest run_id does not match run context")
    best_directory = run_directory / summary["best"]["run_directory"]
    for name in ("rc_lowpass.cir", "ac_results.dat", "ngspice.log"):
        if not (best_directory / name).is_file():
            raise RuntimeError(f"clean best run is missing '{name}'")
    connection = sqlite3.connect(run_directory / "experiments.sqlite3")
    try:
        count = connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    finally:
        connection.close()
    if count != 1:
        raise RuntimeError(f"clean database contains {count} experiments instead of 1")


def build_parser() -> argparse.ArgumentParser:
    """Build command-line options for the standalone clean-environment test."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a fresh venv, install CircuitPilot, run real ngspice optimization, "
            "and verify research artifacts."
        )
    )
    parser.add_argument(
        "--ngspice",
        default="ngspice",
        help="ngspice executable name or full path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the clean install and real end-to-end verification."""
    args = build_parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    ngspice = _resolve_ngspice(project_root, args.ngspice)
    lock_path = project_root / RESEARCH_LOCK_FILENAME
    if not lock_path.is_file():
        print(f"clean_environment_test: FAIL: missing {lock_path}", file=sys.stderr)
        return 1
    try:
        git_commit, git_dirty = _git_source_identity(project_root)
    except (OSError, RuntimeError) as exc:
        print(f"clean_environment_test: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"Project: {project_root}")
    print(f"ngspice: {ngspice}")
    print(f"Research lock: {lock_path}")

    try:
        with tempfile.TemporaryDirectory(prefix="circuitpilot-clean-") as temporary:
            root = Path(temporary)
            venv_directory = root / "venv"
            work_directory = root / "work"
            run_directory = work_directory / "research_run"
            work_directory.mkdir()
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment["PYTHONNOUSERSITE"] = "1"
            environment["PYTHONUTF8"] = "1"
            environment["PYTHONIOENCODING"] = "utf-8"
            environment["CIRCUITPILOT_GIT_COMMIT"] = git_commit
            environment["CIRCUITPILOT_GIT_DIRTY"] = "1" if git_dirty else "0"

            _run_checked(
                [sys.executable, "-m", "venv", str(venv_directory)],
                cwd=work_directory,
                environment=environment,
            )
            python = _venv_python(venv_directory)
            _run_checked(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "-r",
                    str(lock_path),
                ],
                cwd=work_directory,
                environment=environment,
            )
            _run_checked(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-deps",
                    "--no-build-isolation",
                    str(project_root),
                ],
                cwd=work_directory,
                environment=environment,
            )
            _run_checked(
                [str(python), "-m", "pip", "check"],
                cwd=work_directory,
                environment=environment,
            )
            _run_checked(
                [
                    str(python),
                    "-c",
                    "import circuitpilot; print('installed CircuitPilot', circuitpilot.__version__)",
                ],
                cwd=work_directory,
                environment=environment,
            )

            config_path = work_directory / "clean_optimization.yaml"
            _write_clean_optimization_config(config_path)
            _run_checked(
                [
                    str(python),
                    "-m",
                    "circuitpilot",
                    "--optimize-config",
                    str(config_path),
                    "--output-dir",
                    str(run_directory),
                    "--ngspice",
                    str(ngspice),
                    "--experiment-name",
                    "clean environment real E2E",
                    "--experiment-database",
                    str(run_directory / "experiments.sqlite3"),
                ],
                cwd=work_directory,
                environment=environment,
            )
            _verify_artifacts(run_directory, git_commit)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"clean_environment_test: FAIL: {exc}", file=sys.stderr)
        return 1

    print("clean_environment_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
