"""Validated, reproducible MOSFET model-library configuration."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from typing import Any, Mapping

from circuitpilot.exceptions import ConfigError


@dataclass(frozen=True, slots=True)
class MosfetModelConfig:
    """Location and provenance of one externally supplied MOSFET model.

    CircuitPilot never substitutes a built-in or synthetic model.  The model
    path is resolved from YAML (with optional environment-variable expansion)
    and must name an existing regular file before a netlist is generated.
    """

    model_library: Path
    model_name: str
    corner: str
    provenance: str
    model_section: str | None = None
    device_kind: str = "mosfet"

    def __post_init__(self) -> None:
        if not isinstance(self.model_library, Path):
            raise ValueError("mosfet_model.model_library must be a pathlib.Path")
        for name, value in (
            ("model_name", self.model_name),
            ("corner", self.corner),
            ("provenance", self.provenance),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"mosfet_model.{name} must be non-empty")
        if self.model_section is not None and (
            not isinstance(self.model_section, str) or not self.model_section.strip()
        ):
            raise ValueError("mosfet_model.model_section must be null or non-empty")
        if self.device_kind not in {"mosfet", "subcircuit"}:
            raise ValueError("mosfet_model.device_kind must be mosfet or subcircuit")

    def require_library(self) -> Path:
        """Return the absolute model path or fail without a fallback model."""
        source = self.model_library.resolve()
        if not source.is_file():
            raise ConfigError(
                f"MOSFET model library does not exist: '{source}'; "
                "CircuitPilot will not substitute an ideal or synthetic model"
            )
        return source

    def library_sha256(self) -> str:
        """Hash the exact model-library bytes used by ngspice."""
        source = self.require_library()
        digest = sha256()
        try:
            with source.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ConfigError(f"failed to hash MOSFET model library '{source}': {exc}") from exc
        return digest.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Return a stable YAML-compatible representation."""
        return {
            "model_library": self.model_library.as_posix(),
            "model_name": self.model_name,
            "corner": self.corner,
            "model_section": self.model_section,
            "device_kind": self.device_kind,
            "provenance": self.provenance,
        }


def mosfet_model_from_mapping(
    value: Mapping[str, Any], *, base_directory: Path | None = None
) -> MosfetModelConfig:
    """Parse a strict MOS model mapping and expand environment variables."""
    if not isinstance(value, Mapping):
        raise ConfigError("mosfet_model must be a YAML mapping")
    required = {"model_library", "model_name", "corner", "provenance"}
    allowed = required | {"model_section", "device_kind"}
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ConfigError(f"mosfet_model is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"mosfet_model contains unknown field(s): {', '.join(unknown)}")
    raw_path = value["model_library"]
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ConfigError("mosfet_model.model_library must be non-empty")
    expanded = os.path.expandvars(os.path.expanduser(raw_path))
    if "$" in expanded or "%" in expanded:
        raise ConfigError(
            "mosfet_model.model_library contains an unresolved environment variable"
        )
    path = Path(expanded)
    if not path.is_absolute():
        path = (base_directory or Path.cwd()) / path
    try:
        return MosfetModelConfig(
            model_library=path.resolve(),
            model_name=value["model_name"],
            corner=value["corner"],
            provenance=value["provenance"],
            model_section=value.get("model_section"),
            device_kind=value.get("device_kind", "mosfet"),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
