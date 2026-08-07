"""Unique, non-overwriting research run directory lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from circuitpilot.exceptions import RunDirectoryError


RUN_CONTEXT_FILENAME = "run_context.json"
INPUT_CONFIG_FILENAME = "input_config.yaml"
RUN_CONTEXT_SCHEMA_VERSION = 1
_RUN_ID_PATTERN = re.compile(r"^cp-\d{8}T\d{12}Z-[0-9a-f]{12}$")


@dataclass(frozen=True, slots=True)
class ResearchRunDirectory:
    """Prepared filesystem boundary for exactly one research experiment."""

    path: Path
    run_id: str
    resumed: bool
    resume_count: int


def generate_run_id() -> str:
    """Return a sortable UTC identifier with collision-resistant entropy."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"cp-{timestamp}-{uuid4().hex[:12]}"


def _write_context(path: Path, context: dict[str, object]) -> None:
    """Atomically write one run context JSON document."""
    destination = path / RUN_CONTEXT_FILENAME
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RunDirectoryError(
            f"failed to write run context '{destination}': {exc}"
        ) from exc


def _new_context(
    run_id: str, configuration_sha256: str | None = None
) -> dict[str, object]:
    """Build the immutable identity and initial lifecycle fields for a run."""
    context: dict[str, object] = {
        "schema_version": RUN_CONTEXT_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "resume_count": 0,
        "status": "incomplete",
    }
    if configuration_sha256 is not None:
        context["configuration_sha256"] = configuration_sha256
    return context


def _load_context(path: Path) -> dict[str, object]:
    """Load and validate the context required for safe resume."""
    source = path / RUN_CONTEXT_FILENAME
    try:
        loaded = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunDirectoryError(
            f"cannot resume '{path}': missing {RUN_CONTEXT_FILENAME}"
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunDirectoryError(f"cannot resume '{path}': invalid run context: {exc}") from exc
    if not isinstance(loaded, dict):
        raise RunDirectoryError(f"cannot resume '{path}': run context must be an object")
    run_id = loaded.get("run_id")
    resume_count = loaded.get("resume_count")
    if not isinstance(run_id, str) or _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise RunDirectoryError(f"cannot resume '{path}': invalid run_id")
    if (
        isinstance(resume_count, bool)
        or not isinstance(resume_count, int)
        or resume_count < 0
    ):
        raise RunDirectoryError(f"cannot resume '{path}': invalid resume_count")
    if loaded.get("schema_version") != RUN_CONTEXT_SCHEMA_VERSION:
        raise RunDirectoryError(f"cannot resume '{path}': unsupported run context schema")
    return loaded


def prepare_research_run_directory(
    output_directory: str | Path | None,
    *,
    resume: bool = False,
    default_root: str | Path = "output",
    source_config: str | Path | None = None,
    configuration_sha256: str | None = None,
) -> ResearchRunDirectory:
    """Create a unique run directory or explicitly resume an existing one.

    If ``output_directory`` is omitted, an atomically created ``<default_root>/<run_id>``
    directory is used. An explicitly requested existing non-empty directory is
    always rejected unless ``resume`` is true. Resume additionally requires a
    valid context created by CircuitPilot, preventing accidental adoption of an
    unrelated directory.
    """
    if resume and output_directory is None:
        raise RunDirectoryError("--resume requires an explicit --output-dir")
    if configuration_sha256 is not None and re.fullmatch(
        r"[0-9a-f]{64}", configuration_sha256
    ) is None:
        raise RunDirectoryError("configuration_sha256 must be 64 lowercase hex characters")

    if output_directory is None:
        root = Path(default_root).resolve()
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RunDirectoryError(
                f"failed to create default output root '{root}': {exc}"
            ) from exc
        for _ in range(10):
            run_id = generate_run_id()
            destination = root / run_id
            try:
                destination.mkdir(exist_ok=False)
            except FileExistsError:
                continue
            except OSError as exc:
                raise RunDirectoryError(
                    f"failed to create run directory '{destination}': {exc}"
                ) from exc
            _write_context(destination, _new_context(run_id, configuration_sha256))
            return ResearchRunDirectory(destination, run_id, False, 0)
        raise RunDirectoryError("failed to allocate a unique run_id after 10 attempts")

    destination = Path(output_directory).resolve()
    if destination.exists() and not destination.is_dir():
        raise RunDirectoryError(f"output path is not a directory: '{destination}'")
    try:
        existing_entries = tuple(destination.iterdir()) if destination.exists() else ()
    except OSError as exc:
        raise RunDirectoryError(f"failed to inspect output directory '{destination}': {exc}") from exc

    if existing_entries:
        if not resume:
            raise RunDirectoryError(
                f"output directory is not empty: '{destination}'; choose a new "
                "directory or pass --resume to resume this run"
            )
        context = _load_context(destination)
        if configuration_sha256 is not None:
            original_fingerprint = context.get("configuration_sha256")
            if original_fingerprint != configuration_sha256:
                raise RunDirectoryError(
                    "resume configuration does not match the original resolved configuration"
                )
        if source_config is not None:
            original_config = destination / INPUT_CONFIG_FILENAME
            try:
                incoming_payload = Path(source_config).resolve().read_bytes()
                original_payload = original_config.read_bytes()
            except OSError as exc:
                raise RunDirectoryError(
                    f"cannot verify resume configuration in '{destination}': {exc}"
                ) from exc
            if original_payload != incoming_payload:
                raise RunDirectoryError(
                    "resume configuration does not match the original input_config.yaml"
                )
        resume_count = int(context["resume_count"]) + 1
        context["resume_count"] = resume_count
        context["last_resumed_at_utc"] = datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        )
        context["status"] = "incomplete"
        _write_context(destination, context)
        return ResearchRunDirectory(
            destination,
            str(context["run_id"]),
            True,
            resume_count,
        )

    if resume:
        raise RunDirectoryError(
            f"cannot resume empty output directory '{destination}'"
        )
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RunDirectoryError(f"failed to create output directory '{destination}': {exc}") from exc
    run_id = generate_run_id()
    _write_context(destination, _new_context(run_id, configuration_sha256))
    return ResearchRunDirectory(destination, run_id, False, 0)


def mark_run_successful(output_directory: str | Path, run_id: str) -> None:
    """Mark the matching run context successful before manifest inventory."""
    destination = Path(output_directory).resolve()
    context = _load_context(destination)
    if context["run_id"] != run_id:
        raise RunDirectoryError(
            f"run_id '{run_id}' does not match context '{context['run_id']}'"
        )
    context["status"] = "success"
    context["completed_at_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    )
    _write_context(destination, context)


def snapshot_run_input_config(
    run: ResearchRunDirectory, source_config: str | Path | None
) -> Path | None:
    """Snapshot YAML at run start and reject config changes during resume."""
    if source_config is None:
        return None
    source = Path(source_config).resolve()
    destination = run.path / INPUT_CONFIG_FILENAME
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise RunDirectoryError(f"failed to read input configuration '{source}': {exc}") from exc
    if run.resumed and destination.is_file():
        try:
            existing = destination.read_bytes()
        except OSError as exc:
            raise RunDirectoryError(
                f"failed to verify resumed configuration '{destination}': {exc}"
            ) from exc
        if existing != payload:
            raise RunDirectoryError(
                "resume configuration does not match the original input_config.yaml"
            )
        return destination
    try:
        destination.write_bytes(payload)
    except OSError as exc:
        raise RunDirectoryError(
            f"failed to snapshot input configuration '{destination}': {exc}"
        ) from exc
    return destination
