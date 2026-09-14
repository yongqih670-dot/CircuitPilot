"""Safe subprocess boundary for invoking ngspice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from time import monotonic

from circuitpilot.exceptions import SimulationError


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Captured information from a successful ngspice process."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


def resolve_ngspice_executable(executable: str = "ngspice") -> str | None:
    """Resolve ngspice, including the project-local Windows portable build.

    The official Windows archive contains both a GUI-oriented ``ngspice.exe``
    and a console ``ngspice_con.exe``. Batch automation prefers the console
    binary. When ``ngspice`` is not on ``PATH``, source checkouts also search
    ``tools/ngspice/bin`` beneath the working directory and project root.
    """
    resolved = shutil.which(executable)
    if resolved is not None:
        resolved_path = Path(resolved)
        if resolved_path.name.lower() == "ngspice.exe":
            console_binary = resolved_path.with_name("ngspice_con.exe")
            if console_binary.is_file():
                return str(console_binary)
        return resolved

    if executable.lower() != "ngspice":
        return None
    candidates = (
        Path.cwd() / "tools" / "ngspice" / "bin" / "ngspice_con.exe",
        Path(__file__).resolve().parents[2]
        / "tools"
        / "ngspice"
        / "bin"
        / "ngspice_con.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def run_ngspice(
    netlist_path: str | Path,
    *,
    executable: str = "ngspice",
    timeout_seconds: float = 60.0,
    log_path: str | Path | None = None,
    preserve_runtime_paths: bool = False,
) -> SimulationResult:
    """Run ngspice in batch mode and require a successful exit status.

    Args:
        netlist_path: Existing SPICE netlist to execute.
        executable: ngspice executable name or path.
        timeout_seconds: Maximum runtime before the process is terminated.
        log_path: Optional ngspice log destination supplied with ``-o``.
        preserve_runtime_paths: Keep caller-provided drive aliases instead of
            resolving them to a potentially long or non-ASCII physical path.

    Returns:
        Captured process metadata for a successful execution.

    Raises:
        ValueError: If ``timeout_seconds`` is not positive.
        SimulationError: If inputs are missing, ngspice cannot start, times
            out, or returns a non-zero status.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    source = (
        Path(netlist_path).absolute()
        if preserve_runtime_paths
        else Path(netlist_path).resolve()
    )
    if not source.is_file():
        raise SimulationError(f"netlist does not exist: '{source}'")

    resolved_executable = resolve_ngspice_executable(executable)
    if resolved_executable is None:
        raise SimulationError(
            f"ngspice executable '{executable}' was not found; "
            "install ngspice or pass --ngspice with its full path"
        )

    command = [resolved_executable, "-b"]
    if log_path is not None:
        log_destination = (
            Path(log_path).absolute()
            if preserve_runtime_paths
            else Path(log_path).resolve()
        )
        try:
            log_destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SimulationError(
                f"failed to create log directory '{log_destination.parent}': {exc}"
            ) from exc
        command.extend(["-o", str(log_destination)])
    command.append(str(source))

    started_at = monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=source.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SimulationError(
            f"ngspice timed out after {timeout_seconds:g} seconds",
            timed_out=True,
        ) from exc
    except OSError as exc:
        raise SimulationError(f"failed to start ngspice: {exc}") from exc

    elapsed = monotonic() - started_at
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        if len(details) > 1_000:
            details = details[-1_000:]
        suffix = f": {details}" if details else ""
        raise SimulationError(
            f"ngspice exited with status {completed.returncode}{suffix}",
            returncode=completed.returncode,
        )

    return SimulationResult(
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        elapsed_seconds=elapsed,
    )
