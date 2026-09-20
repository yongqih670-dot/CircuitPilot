"""Real multi-corner SKY130 runtime paths for Task 9."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields
from hashlib import sha256
from pathlib import Path
import shutil
import tempfile
from threading import Lock
from types import SimpleNamespace
from typing import Any, Iterator

from circuitpilot.exceptions import ConfigError
from circuitpilot.sky130_common_source import NgspiceRuntimePaths
from circuitpilot.sky130_model import Sky130ModelConfig
from circuitpilot.sky130_two_stage_ota import Sky130TwoStageOtaCircuitConfig
from circuitpilot.task9_protocol import CORNER_BY_ID, PVTCorner


_CACHE_LOCK = Lock()


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def task9_corner_model_paths(
    model: Sky130ModelConfig, process_corner: str
) -> tuple[Path, Path, Path]:
    if process_corner not in {corner.process_corner for corner in CORNER_BY_ID.values()}:
        raise ConfigError(f"unknown Task 9 process corner '{process_corner}'")
    identity = model.expected_model_sha256 or model.model_sha256()
    cache = (
        Path(tempfile.gettempdir())
        / "circuitpilot-task9-pvt-model-cache"
        / identity[:20]
        / process_corner
    )
    primitive_root = model.pdk_root / "libs.ref" / "sky130_fd_pr" / "spice"
    sources = [model.invariant_path]
    for polarity in ("nfet", "pfet"):
        for suffix in ("corner", "pm3"):
            sources.append(
                primitive_root
                / f"sky130_fd_pr__{polarity}_01v8__{process_corner}.{suffix}.spice"
            )
    for source in sources:
        if not source.is_file():
            raise ConfigError(f"missing real Task 9 corner fragment: '{source}'")
    content_identity = sha256(
        "\0".join(f"{source.name}:{_sha256(source)}" for source in sources).encode("ascii")
    ).hexdigest()
    marker = cache / "content_sha256.txt"
    with _CACHE_LOCK:
        ready = (
            marker.is_file()
            and marker.read_text(encoding="ascii").strip() == content_identity
            and all((cache / source.name).is_file() for source in sources)
        )
        if not ready:
            cache.mkdir(parents=True, exist_ok=True)
            for source in sources:
                temporary = cache / f".{source.name}.tmp"
                shutil.copyfile(source, temporary)
                temporary.replace(cache / source.name)
            marker.write_text(content_identity + "\n", encoding="ascii")
    return (
        cache / model.invariant_path.name,
        cache / f"sky130_fd_pr__nfet_01v8__{process_corner}.corner.spice",
        cache / f"sky130_fd_pr__pfet_01v8__{process_corner}.corner.spice",
    )


def task9_corner_config(
    base: Sky130TwoStageOtaCircuitConfig, corner: PVTCorner
) -> Any:
    """Return a read-only duck-typed Task 7 config with corner VDD/temperature."""
    values = {field.name: getattr(base, field.name) for field in fields(base)}
    values["supply_voltage_v"] = corner.vdd_v
    values["temperature_c"] = corner.temperature_c
    return SimpleNamespace(**values)


@contextmanager
def task9_runtime_paths(
    model: Sky130ModelConfig,
    process_corner: str,
    evaluation_directory: Path,
) -> Iterator[NgspiceRuntimePaths]:
    """Expose short ASCII paths for one real process corner and retain evidence."""
    directory = evaluation_directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    netlist = directory / "circuit.cir"
    data = directory / "data.dat"
    op = directory / "op.dat"
    device = directory / "device_op.dat"
    log = directory / "ngspice.log"
    staging = Path(tempfile.mkdtemp(prefix="circuitpilot-task9-"))
    invariant, nfet, pfet = task9_corner_model_paths(model, process_corner)
    try:
        yield NgspiceRuntimePaths(
            netlist,
            data,
            op,
            device,
            log,
            staging / netlist.name,
            (staging / data.name).as_posix(),
            (staging / op.name).as_posix(),
            (staging / device.name).as_posix(),
            staging / log.name,
            invariant.as_posix(),
            nfet.as_posix(),
            pfet.as_posix(),
        )
    finally:
        for source in staging.iterdir():
            if source.is_file():
                destination = directory / source.name
                try:
                    shutil.copy2(source, destination)
                except OSError:
                    shutil.copy2(source, Path("\\\\?\\" + str(destination)))
        shutil.rmtree(staging, ignore_errors=True)
