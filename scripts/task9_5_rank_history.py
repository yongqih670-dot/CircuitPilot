"""Rank immutable complete Task 9 matrices under the frozen v2 semantics."""

from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path

from circuitpilot.task9_5_region import V2_SEMANTICS, classify_device
from circuitpilot.sky130_two_stage_ota import DEVICE_ROLES, PFET_ROLES
from circuitpilot.task9_protocol import STAGE_COMPONENTS, corner_constraint_components


ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    ROOT / "research/sky130/two_stage_ota/task9/nominal_gap/full_pvt_matrix.jsonl",
    ROOT / "research/sky130/two_stage_ota/task9/calibration/full_pvt/full_pvt_matrix.jsonl",
)
OUTPUT = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/history_rank.csv"


def main() -> None:
    rows = []
    for path in INPUTS:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                passing = 0
                region_passing = 0
                violations = Counter()
                devices = Counter()
                worst = 0.0
                for corner in item["corners"]:
                    quantities = corner["evidence"].get("device_quantities", {})
                    region = all(classify_device(
                        quantities.get(role, {}), version=V2_SEMANTICS,
                        pfet=role in PFET_ROLES,
                    ) == "saturation" for role in DEVICE_ROLES)
                    region_passing += region
                    metrics = dict(corner["metrics"])
                    metrics["operating_region_valid"] = float(region)
                    components = corner_constraint_components(metrics, corner["statuses"])
                    for name, value in components.items():
                        if value > 0:
                            violations[name] += 1
                            worst = max(worst, value)
                    passing += all(value == 0 for value in components.values())
                    for role in DEVICE_ROLES:
                        if classify_device(quantities.get(role, {}), version=V2_SEMANTICS,
                                           pfet=role in PFET_ROLES) != "saturation":
                            devices[role] += 1
                rows.append({
                    "source": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "design_id": item["design_id"],
                    "passing_corners_v2": passing,
                    "region_passing_corners_v2": region_passing,
                    "worst_normalized_violation": worst,
                    "constraint_failure_counts": json.dumps(violations, sort_keys=True),
                    "device_failure_counts": json.dumps(devices, sort_keys=True),
                    "parameters": json.dumps(item["parameters"], sort_keys=True),
                })
    rows.sort(key=lambda row: (-row["passing_corners_v2"],
                               -row["region_passing_corners_v2"],
                               row["worst_normalized_violation"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"count": len(rows), "top": rows[:5]}, indent=2))


if __name__ == "__main__":
    main()
