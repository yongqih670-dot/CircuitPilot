"""Fail-closed, evidence-backed gate for future Task 10 formal execution."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
from hashlib import sha256
import json
from math import exp, isclose, log
from pathlib import Path
from typing import Any, Mapping
from zipfile import BadZipFile, ZipFile

from circuitpilot.environment_fingerprint import collect_environment_fingerprint
from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.task9_protocol import CANONICAL_CORNER_ORDER, CORNER_BY_ID, PVT_BENCHMARK_HASH
from circuitpilot.task9_5_benchmark import benchmark_v2_hash
from circuitpilot.task9_5_region import V2_SEMANTICS
from circuitpilot.task9_6_feedback import summarize_v2_robust_feedback
from circuitpilot.task9_6_v2_evaluator import APPROVED_BENCHMARK_V2_HASH


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GATE = ROOT / "research/sky130/two_stage_ota/task9_6/task10_execution_gate.json"
FROZEN_TASK7 = ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml"
ENVIRONMENT_LOCK_FIELDS = (
    "ngspice_executable_sha256", "ngspice_version_string",
    "python_implementation", "python_version", "numpy_version",
    "scipy_version", "pyyaml_version", "optuna_version",
    "research_baseline_version", "os_information",
)


@dataclass(frozen=True, slots=True)
class GuardDecision:
    allowed: bool
    reasons: tuple[str, ...]
    benchmark_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reasons": list(self.reasons),
                "benchmark_hash": self.benchmark_hash}


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _locked_file(reference: Mapping[str, str]) -> tuple[Path, bytes]:
    if not isinstance(reference, Mapping):
        raise ValueError("missing hashed evidence reference")
    relative = reference.get("path")
    expected = reference.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("invalid hashed evidence reference")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError("evidence path missing or escapes repository")
    data = path.read_bytes()
    if _digest(data) != expected:
        raise ValueError(f"evidence SHA-256 mismatch: {relative}")
    return path, data


def _locked_json(reference: Mapping[str, str]) -> dict[str, Any]:
    path, data = _locked_file(reference)
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("evidence JSON must be an object")
    return value


def _wrapper(reference: Mapping[str, str], *, mode: str) -> dict[str, Any]:
    wrapper = _locked_json(reference)
    if wrapper.get("schema_version") != "task9_6_v2_evaluation_v1":
        raise ValueError("witness/validation matrix is not a Task 9.6 v2 wrapper")
    if wrapper.get("benchmark_v2_hash") != APPROVED_BENCHMARK_V2_HASH:
        raise ValueError("matrix benchmark hash mismatch")
    raw = wrapper.get("raw_v2_result")
    if not isinstance(raw, dict) or raw.get("mode") != mode:
        raise ValueError(f"expected {mode} v2 matrix")
    feedback = summarize_v2_robust_feedback(raw)
    if wrapper.get("robust_feedback") != feedback:
        raise ValueError("stored robust feedback differs from recomputation")
    return wrapper


def _full_positive(wrapper: Mapping[str, Any]) -> None:
    raw = wrapper["raw_v2_result"]
    feedback = wrapper["robust_feedback"]
    if (raw.get("process_calls") != 45 or raw.get("complete_full_matrix") is not True
            or raw.get("is_feasible") is not True
            or feedback["robust_evaluation_status"] != "exact"
            or feedback["exact_robust_violation"] != 0.0):
        raise ValueError("Full-PVT witness is not a complete 45-analysis positive")
    for corner in raw["corners"]:
        descriptor = CORNER_BY_ID[corner["corner_id"]]
        if any(corner.get(key) != value for key, value in descriptor.to_dict().items()):
            raise ValueError("corner identity/application descriptor mismatch")
        if (set(corner["completed_analyses"]) != {"op", "ac", "transient"}
                or any(corner["analysis_errors"].values())
                or not all(corner["application_checks"].values())):
            raise ValueError("witness analysis error or failed corner application")


def _hierarchical_positive(wrapper: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
    raw = wrapper["raw_v2_result"]
    if (raw.get("parameters") != parameters or raw.get("is_feasible") is not True
            or raw.get("first_failure") is not None or raw.get("process_calls") != 45
            or wrapper["robust_feedback"]["measured_analysis_count"] != 45):
        raise ValueError("real positive was rejected or incomplete in Hierarchical-PVT")


def _environment_lock(fingerprint: Mapping[str, Any]) -> str:
    if any(name not in fingerprint for name in ENVIRONMENT_LOCK_FIELDS):
        raise ValueError("environment fingerprint missing locked fields")
    payload = {name: fingerprint[name] for name in ENVIRONMENT_LOCK_FIELDS}
    return _digest(json.dumps(payload, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode())


def _expected_neighborhood(parameters: Mapping[str, float], search_space: Any) -> list[dict[str, float]]:
    by_name = {item.name: item for item in search_space}
    expected = []
    for name in ("input_pair_length_m", "first_stage_load_width_m", "second_load_bias_v"):
        item = by_name[name]
        low, high = float(item.low), float(item.high)
        value = float(parameters[name])
        position = ((log(value) - log(low)) / (log(high) - log(low)) if item.log
                    else (value - low) / (high - low))
        if position <= 0.02:
            deltas = (0.01, 0.02)
        elif position >= 0.98:
            deltas = (-0.01, -0.02)
        else:
            deltas = (-0.01, 0.01)
        for delta in deltas:
            shifted = position + delta
            changed = (exp(log(low) + shifted * (log(high) - log(low))) if item.log
                       else low + shifted * (high - low))
            candidate = dict(parameters)
            candidate[name] = changed
            expected.append(candidate)
    return expected


def _check_neighborhood(reference: Mapping[str, str], witness_parameters: Mapping[str, float],
                        search_space: Any) -> None:
    audit = _locked_json(reference)
    if (audit.get("schema_version") != "task9_6_neighborhood_audit_v1"
            or audit.get("benchmark_v2_hash") != APPROVED_BENCHMARK_V2_HASH
            or audit.get("complete") is not True):
        raise ValueError("neighborhood audit is incomplete or wrong benchmark")
    entries = audit.get("entries")
    if not isinstance(entries, list) or len(entries) != 6:
        raise ValueError("pre-registered six-neighbor audit is incomplete")
    expected = _expected_neighborhood(witness_parameters, search_space)
    seen = set()
    for entry in entries:
        full = _wrapper(entry["full_matrix"], mode="full")
        hierarchical = _wrapper(entry["hierarchical_matrix"], mode="hierarchical")
        full_raw = full["raw_v2_result"]
        hierarchical_raw = hierarchical["raw_v2_result"]
        if (full["robust_feedback"]["robust_evaluation_status"] != "exact"
                or hierarchical_raw.get("parameters") != full_raw.get("parameters")
                or hierarchical_raw.get("is_feasible") != full_raw.get("is_feasible")):
            raise ValueError("neighborhood Full/Hierarchical feasibility mismatch")
        if full_raw.get("is_feasible"):
            _full_positive(full)
            _hierarchical_positive(hierarchical, full_raw["parameters"])
        parameter_hash = _digest(json.dumps(full_raw["parameters"], sort_keys=True,
                                           separators=(",", ":"), allow_nan=False).encode())
        if parameter_hash in seen:
            raise ValueError("duplicate neighborhood parameter vector")
        seen.add(parameter_hash)
        matches = [index for index, candidate in enumerate(expected)
                   if set(candidate) == set(full_raw["parameters"])
                   and all(isclose(float(candidate[name]),
                                   float(full_raw["parameters"][name]),
                                   rel_tol=1e-12, abs_tol=1e-30)
                           for name in candidate)]
        if len(matches) != 1:
            raise ValueError("neighbor is not a preregistered witness perturbation")
        del expected[matches[0]]
    if expected:
        raise ValueError("pre-registered neighborhood perturbation missing")


def _check_raw_witness(manifest_ref: Mapping[str, str], archive_ref: Mapping[str, str],
                       matrix_sha: str, frozen_model: Any) -> None:
    manifest = _locked_json(manifest_ref)
    archive_path, archive_bytes = _locked_file(archive_ref)
    if (manifest.get("schema_version") != "task9_6_raw_witness_manifest_v1"
            or manifest.get("benchmark_v2_hash") != APPROVED_BENCHMARK_V2_HASH
            or manifest.get("matrix_sha256") != matrix_sha
            or manifest.get("raw_archive_sha256") != _digest(archive_bytes)
            or manifest.get("pdk_commit") != frozen_model.pdk_commit
            or manifest.get("model_sha256") != frozen_model.model_sha256()
            or manifest.get("model_library_sha256") != frozen_model.library_sha256()):
        raise ValueError("raw witness manifest does not bind PDK/model/matrix/archive")
    sections = manifest.get("corner_model_sections")
    if not isinstance(sections, dict) or set(sections) != set(CANONICAL_CORNER_ORDER):
        raise ValueError("raw witness model-section inventory incomplete")
    if any(sections[corner] != CORNER_BY_ID[corner].process_corner
           for corner in CANONICAL_CORNER_ORDER):
        raise ValueError("raw witness model-section identity mismatch")
    model_hash_prefix = frozen_model.model_sha256()[:20]
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("raw witness ZIP failed CRC verification")
        names = archive.namelist()
        for corner in CANONICAL_CORNER_ORDER:
            descriptor = CORNER_BY_ID[corner]
            for stage in ("op", "ac", "transient"):
                files = ("circuit.cir", "ngspice.log", "op.dat", "device_op.dat") if stage == "op" else ("circuit.cir", "ngspice.log", "data.dat")
                for filename in files:
                    suffix = f"/{corner}/{stage}/{filename}"
                    matches = [name for name in names if name.endswith(suffix)]
                    if len(matches) != 1:
                        raise ValueError(f"missing raw witness {corner}/{stage}/{filename}")
                    if filename == "circuit.cir":
                        netlist = archive.read(matches[0]).decode("utf-8")
                        expected_temp = f".temp {descriptor.temperature_c:.12g}"
                        expected_vdd = f"VDD vdd 0 DC {descriptor.vdd_v:.12g}"
                        expected_section = f"__{descriptor.process_corner}.corner.spice"
                        if (expected_temp not in netlist or expected_vdd not in netlist
                                or netlist.count(expected_section) < 2
                                or model_hash_prefix not in netlist):
                            raise ValueError(f"raw witness netlist corner/model mismatch: {corner}/{stage}")


def check_task10_execution_guard(gate_path: Path = DEFAULT_GATE) -> GuardDecision:
    """Check actual machine evidence; never run a formal simulation here."""
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if not isinstance(gate, dict):
            raise ValueError("gate must be a JSON object")
        reasons = []
        if gate.get("schema_version") != "task10_execution_gate_v1":
            reasons.append("unsupported gate schema")
        if benchmark_v2_hash() != APPROVED_BENCHMARK_V2_HASH:
            reasons.append("installed corrected benchmark definition differs from approved hash")
        if (gate.get("approved_corrected_benchmark_hash") != APPROVED_BENCHMARK_V2_HASH
                or gate.get("selected_benchmark_hash") != APPROVED_BENCHMARK_V2_HASH
                or gate.get("selected_benchmark_hash") == PVT_BENCHMARK_HASH
                or gate.get("old_task9_benchmark_hash") != PVT_BENCHMARK_HASH
                or gate.get("region_semantics") != V2_SEMANTICS):
            reasons.append("old, unapproved or non-v2 benchmark identity")
        for flag in ("verified_real_pvt_witness", "positive_screening_validation",
                     "neighborhood_consistency_audit_complete", "witness_matrix_complete",
                     "corner_application_checks_pass"):
            if gate.get(flag) is not True:
                reasons.append(f"{flag} is not true")
        if (gate.get("corner_count") != 15 or gate.get("analysis_count") != 45
                or gate.get("analysis_errors") != 0):
            reasons.append("15-corner/45-analysis/zero-error count gate is not satisfied")
        if reasons:
            return GuardDecision(False, tuple(reasons), gate.get("selected_benchmark_hash"))

        frozen = load_experiment_config(FROZEN_TASK7)
        model = frozen.circuit_config.model
        if (gate.get("pdk_commit") != model.pdk_commit
                or gate.get("model_sha256") != model.model_sha256()
                or gate.get("model_library_sha256") != model.library_sha256()):
            raise ValueError("current PDK/model hashes do not match locked gate")
        witness = _wrapper(gate["witness_matrix"], mode="full")
        _full_positive(witness)
        hierarchy = _wrapper(gate["hierarchical_validation_matrix"], mode="hierarchical")
        _hierarchical_positive(hierarchy, witness["raw_v2_result"]["parameters"])
        _check_neighborhood(gate["neighborhood_audit"],
                            witness["raw_v2_result"]["parameters"], frozen.search_space)
        _check_raw_witness(gate["witness_raw_manifest"], gate["witness_raw_archive"],
                           gate["witness_matrix"]["sha256"], model)
        fingerprint = _locked_json(gate["environment_fingerprint"])
        environment_hash = _environment_lock(fingerprint)
        if gate.get("environment_lock_sha256") != environment_hash:
            raise ValueError("witness environment lock hash mismatch")
        current = collect_environment_fingerprint(fingerprint["ngspice_executable_path"])
        if _environment_lock(current) != environment_hash:
            raise ValueError("current simulation environment differs from witness")
        return GuardDecision(True, (), APPROVED_BENCHMARK_V2_HASH)
    except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile,
            json.JSONDecodeError) as exc:
        return GuardDecision(False, (f"invalid or missing release evidence: {exc}",), None)


def require_task10_execution_guard(gate_path: Path = DEFAULT_GATE) -> None:
    decision = check_task10_execution_guard(gate_path)
    if not decision.allowed:
        raise RuntimeError("Task 10 formal execution blocked: " + "; ".join(decision.reasons))
