"""Discovery, provenance validation, and content locking for SKY130 models."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping

from circuitpilot.exceptions import ConfigError


SKY130_DEVICE_NAME = "sky130_fd_pr__nfet_01v8"
SKY130_MODEL_SOURCE = "FOSSi Foundation Ciel/Open_PDKs prebuilt SKY130"


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sha256(value: str | None, field: str) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex string")


def _find_variant_root(candidate: Path) -> Path:
    resolved = candidate.expanduser().resolve()
    possibilities = (resolved, resolved / "sky130A")
    for path in possibilities:
        if (path / "libs.tech" / "ngspice" / "sky130.lib.spice").is_file():
            return path
    raise ConfigError(
        f"SKY130 PDK root '{resolved}' does not contain "
        "sky130A/libs.tech/ngspice/sky130.lib.spice"
    )


def _infer_variant_root(library: Path) -> Path:
    for parent in library.resolve().parents:
        if (
            (parent / "libs.tech" / "ngspice" / "sky130.lib.spice").is_file()
            and (parent / "libs.ref" / "sky130_fd_pr" / "spice").is_dir()
        ):
            return parent
    raise ConfigError(
        f"cannot infer a complete SKY130A Open_PDKs root from '{library.resolve()}'"
    )


@lru_cache(maxsize=16)
def _model_tree_sha256_cached(variant_root_text: str) -> tuple[str, int]:
    root = Path(variant_root_text)
    trees = (
        root / "libs.tech" / "ngspice",
        root / "libs.ref" / "sky130_fd_pr" / "spice",
    )
    files: list[tuple[str, Path]] = []
    for tree in trees:
        if not tree.is_dir():
            raise ConfigError(f"required SKY130 model directory is missing: '{tree}'")
        prefix = tree.relative_to(root).as_posix()
        for source in tree.rglob("*"):
            if source.is_file():
                files.append((f"{prefix}/{source.relative_to(tree).as_posix()}", source))
    files.sort(key=lambda item: item[0])
    if not files:
        raise ConfigError(f"SKY130 model tree is empty: '{root}'")
    digest = sha256()
    for relative, source in files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(source).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest(), len(files)


@dataclass(frozen=True, slots=True)
class Sky130ModelConfig:
    """One validated, content-addressed Open_PDKs SKY130A model installation."""

    pdk_root: Path
    model_library: Path
    device_name: str = SKY130_DEVICE_NAME
    corner: str = "tt"
    provenance: str = SKY130_MODEL_SOURCE
    pdk_release: str | None = None
    pdk_commit: str | None = None
    primitive_commit: str | None = None
    expected_model_sha256: str | None = None
    expected_library_sha256: str | None = None

    def __post_init__(self) -> None:
        root = self.pdk_root.expanduser().resolve()
        library = self.model_library.expanduser().resolve()
        object.__setattr__(self, "pdk_root", root)
        object.__setattr__(self, "model_library", library)
        if self.device_name != SKY130_DEVICE_NAME:
            raise ValueError(
                f"Task 4 requires device '{SKY130_DEVICE_NAME}', not '{self.device_name}'"
            )
        if self.corner != "tt":
            raise ValueError("Task 4 currently freezes only the SKY130 TT corner")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("SKY130 provenance must be non-empty")
        _validate_sha256(self.expected_model_sha256, "model_sha256")
        _validate_sha256(self.expected_library_sha256, "library_sha256")
        self.require_files()
        if self.expected_model_sha256 is not None:
            actual = self.model_sha256()
            if actual != self.expected_model_sha256:
                raise ConfigError(
                    "SKY130 model content hash mismatch: "
                    f"expected {self.expected_model_sha256}, found {actual}"
                )
        if self.expected_library_sha256 is not None:
            actual = self.library_sha256()
            if actual != self.expected_library_sha256:
                raise ConfigError(
                    "SKY130 library hash mismatch: "
                    f"expected {self.expected_library_sha256}, found {actual}"
                )

    @property
    def invariant_path(self) -> Path:
        """Return the official nominal invariant-parameter file."""
        return self.pdk_root / "libs.tech" / "ngspice" / "parameters" / "invariant.spice"

    @property
    def corner_path(self) -> Path:
        """Return the official target-device TT corner include."""
        return (
            self.pdk_root
            / "libs.ref"
            / "sky130_fd_pr"
            / "spice"
            / "sky130_fd_pr__nfet_01v8__tt.corner.spice"
        )

    @property
    def nodeinfo_path(self) -> Path:
        return self.pdk_root / ".config" / "nodeinfo.json"

    def require_files(self) -> None:
        """Fail explicitly unless the complete trusted model chain exists."""
        for description, path in (
            ("Open_PDKs ngspice library", self.model_library),
            ("SKY130 invariant parameters", self.invariant_path),
            ("sky130_fd_pr__nfet_01v8 TT corner", self.corner_path),
        ):
            if not path.is_file():
                raise ConfigError(f"missing {description}: '{path}'")

    def library_sha256(self) -> str:
        """Hash the top-level Open_PDKs ngspice library file."""
        return _sha256_file(self.model_library)

    def model_sha256(self) -> str:
        """Hash all ngspice technology and primitive model bytes deterministically."""
        return _model_tree_sha256_cached(str(self.pdk_root))[0]

    def model_file_count(self) -> int:
        return _model_tree_sha256_cached(str(self.pdk_root))[1]

    def nodeinfo(self) -> dict[str, Any]:
        """Read provenance emitted by the Open_PDKs build."""
        if not self.nodeinfo_path.is_file():
            return {}
        try:
            value = json.loads(self.nodeinfo_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigError(f"failed to read SKY130 nodeinfo: {exc}") from exc
        if not isinstance(value, dict):
            raise ConfigError("SKY130 nodeinfo.json must contain a JSON object")
        return value

    def metadata(self) -> dict[str, Any]:
        """Return manifest-ready, auditable model provenance and hashes."""
        nodeinfo = self.nodeinfo()
        return {
            "source": self.provenance,
            "pdk_root": str(self.pdk_root),
            "model_path": str(self.model_library),
            "model_library_sha256": self.library_sha256(),
            "model_sha256": self.model_sha256(),
            "model_file_count": self.model_file_count(),
            "device_name": self.device_name,
            "model_section": self.corner,
            "corner": self.corner,
            "pdk_release": self.pdk_release or nodeinfo.get("build", {}).get("open_pdks"),
            "pdk_commit": self.pdk_commit or nodeinfo.get("commit", {}).get("open_pdks"),
            "primitive_commit": self.primitive_commit
            or nodeinfo.get("primitive", {}).get("sky130_fd_pr"),
            "node": nodeinfo.get("node"),
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a strict YAML-compatible content lock."""
        metadata = self.metadata()
        return {
            "pdk_root": str(self.pdk_root),
            "model_library": str(self.model_library),
            "device_name": self.device_name,
            "corner": self.corner,
            "provenance": self.provenance,
            "pdk_release": metadata["pdk_release"],
            "pdk_commit": metadata["pdk_commit"],
            "primitive_commit": metadata["primitive_commit"],
            "model_sha256": metadata["model_sha256"],
            "library_sha256": metadata["model_library_sha256"],
        }


def sky130_model_from_mapping(
    value: Mapping[str, Any], *, base_directory: Path | None = None
) -> Sky130ModelConfig:
    """Resolve explicit YAML/env locations without any reference-model fallback."""
    if not isinstance(value, Mapping):
        raise ConfigError("circuit_config.sky130_model must be a YAML mapping")
    allowed = {
        "pdk_root",
        "model_library",
        "device_name",
        "corner",
        "provenance",
        "pdk_release",
        "pdk_commit",
        "primitive_commit",
        "model_sha256",
        "library_sha256",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigError(
            "circuit_config.sky130_model contains unknown field(s): "
            + ", ".join(unknown)
        )
    base = (base_directory or Path.cwd()).resolve()

    def resolve_path(raw: Any, field: str) -> Path | None:
        if raw is None:
            return None
        if not isinstance(raw, str) or not raw.strip():
            raise ConfigError(f"circuit_config.sky130_model.{field} must be a path")
        path = Path(os.path.expandvars(raw)).expanduser()
        return path.resolve() if path.is_absolute() else (base / path).resolve()

    explicit_library = resolve_path(
        value.get("model_library") or os.environ.get("SKY130_MODEL_LIBRARY"),
        "model_library",
    )
    explicit_root = resolve_path(
        value.get("pdk_root") or os.environ.get("SKY130_PDK_ROOT"),
        "pdk_root",
    )
    if explicit_library is None and explicit_root is None:
        raise ConfigError(
            "SKY130 is not configured: set SKY130_MODEL_LIBRARY or "
            "SKY130_PDK_ROOT, or provide circuit_config.sky130_model.model_library/"
            "pdk_root in YAML; fallback to the Task 3 N1 model is forbidden"
        )
    root = (
        _find_variant_root(explicit_root)
        if explicit_root is not None
        else _infer_variant_root(explicit_library)  # type: ignore[arg-type]
    )
    library = explicit_library or root / "libs.tech" / "ngspice" / "sky130.lib.spice"
    try:
        return Sky130ModelConfig(
            pdk_root=root,
            model_library=library,
            device_name=value.get("device_name", SKY130_DEVICE_NAME),
            corner=value.get("corner", "tt"),
            provenance=value.get("provenance", SKY130_MODEL_SOURCE),
            pdk_release=value.get("pdk_release"),
            pdk_commit=value.get("pdk_commit"),
            primitive_commit=value.get("primitive_commit"),
            expected_model_sha256=value.get("model_sha256"),
            expected_library_sha256=value.get("library_sha256"),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc
