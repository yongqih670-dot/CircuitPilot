"""Freeze near-constraint corners from existing Task 9.5 Full evidence only."""

from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from circuitpilot.task9_protocol import TASK9_SPECIFICATION


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/full_characterization_matrix.json.gz"
OUTPUT = ROOT / "research/sky130/two_stage_ota/task9_6/near_corner_selection.json"
DEVICE_MARGIN_THRESHOLD_V = 0.01
NORMALIZED_HARD_MARGIN_THRESHOLD = 0.02


def _margin(value, threshold, *, lower):
    if value is None:
        return None
    return ((float(value) - threshold) if lower else (threshold - float(value))) / max(abs(threshold), 1e-30)


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing overwrite: {OUTPUT}")
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        matrix = json.load(handle)
    spec = TASK9_SPECIFICATION
    rules = (
        ("dc_gain_db", spec.gain_min_db, True),
        ("ugf_hz", spec.ugf_min_hz, True),
        ("phase_margin_deg", spec.phase_margin_min_deg, True),
        ("dc_power_w", spec.power_max_w, False),
        ("positive_slew_v_per_s", spec.positive_slew_min_v_per_s, True),
        ("negative_slew_v_per_s", spec.negative_slew_min_v_per_s, True),
        ("output_dc_voltage", spec.output_min_v, True),
        ("output_dc_voltage", spec.output_max_v, False),
    )
    corners = []
    for corner in matrix["corners"]:
        devices = corner["evidence"]["device_quantities"]
        on_min = min(values["vgs"] - values["vth"] for values in devices.values())
        headroom_min = min(values["vds"] - values["vdsat"] for values in devices.values())
        hard_margins = {
            f"{name}_{'min' if lower else 'max'}": _margin(corner["metrics"].get(name),
                                                            threshold, lower=lower)
            for name, threshold, lower in rules
        }
        finite_hard = [value for value in hard_margins.values() if value is not None]
        minimum_hard = min(finite_hard) if finite_hard else None
        failed = any(value > 0 for value in corner["constraint_components"].values())
        near = (failed or on_min <= DEVICE_MARGIN_THRESHOLD_V
                or headroom_min <= DEVICE_MARGIN_THRESHOLD_V
                or minimum_hard is None
                or minimum_hard <= NORMALIZED_HARD_MARGIN_THRESHOLD)
        corners.append({
            "corner_id": corner["corner_id"], "selected": near,
            "baseline_hard_failure": failed,
            "minimum_device_on_margin_v": on_min,
            "minimum_model_vdsat_headroom_v": headroom_min,
            "normalized_hard_margins": hard_margins,
            "minimum_normalized_hard_margin": minimum_hard,
        })
    payload = {
        "schema_version": "task9_6_near_constraint_selection_v1",
        "source_full_matrix_sha256": sha256(gzip.decompress(SOURCE.read_bytes())).hexdigest(),
        "device_margin_threshold_v": DEVICE_MARGIN_THRESHOLD_V,
        "normalized_hard_margin_threshold": NORMALIZED_HARD_MARGIN_THRESHOLD,
        "selected_corner_ids": [row["corner_id"] for row in corners if row["selected"]],
        "corners": corners,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(payload["selected_corner_ids"])


if __name__ == "__main__":
    main()
