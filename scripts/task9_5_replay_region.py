"""Counterfactual region classification from frozen Task 7--9 OP evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from circuitpilot.sky130_two_stage_ota import DEVICE_ROLES, PFET_ROLES  # noqa: E402
from circuitpilot.task9_protocol import STATIC_WORST_FIRST_ORDER, STAGE_COMPONENTS  # noqa: E402
from circuitpilot.task9_5_region import (  # noqa: E402
    V1_SEMANTICS, V2_SEMANTICS, V2_HEADROOM_TOLERANCE_V,
    classify_device, region_semantics_hash,
)


BASE = ROOT / "research/sky130/two_stage_ota"
T95 = BASE / "task9_5/region"
T9 = BASE / "task9"
TRANSITIONS = ("agree_valid", "agree_invalid", "v1_valid_v2_invalid", "v1_invalid_v2_valid")


def rows(path: Path) -> Iterator[dict[str, str]]:
    csv.field_size_limit(1_000_000_000)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def json_lines(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def candidate_key(parameters: Any) -> str:
    if isinstance(parameters, str):
        parameters = json.loads(parameters)
    return sha256(json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def classification(devices: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    v1 = {
        role: classify_device(devices.get(role, {}), version=V1_SEMANTICS,
                              pfet=role in PFET_ROLES)
        for role in DEVICE_ROLES
    }
    v2 = {
        role: classify_device(devices.get(role, {}), version=V2_SEMANTICS,
                              pfet=role in PFET_ROLES)
        for role in DEVICE_ROLES
    }
    return v1, v2


def transition(v1: str, v2: str) -> str:
    first, second = v1 == "saturation", v2 == "saturation"
    if first and second:
        return "agree_valid"
    if not first and not second:
        return "agree_invalid"
    return "v1_valid_v2_invalid" if first else "v1_invalid_v2_valid"


def all_valid(statuses: dict[str, str]) -> bool:
    return all(status == "saturation" for status in statuses.values())


def other_constraints_pass(components: dict[str, Any]) -> bool:
    return all(float(value) <= 0 for name, value in components.items()
               if name != "operating_region")


def classify_corner(
    corner: dict[str, Any], *, benchmark: str, design: str,
    method: str, policy: str, counter: Counter,
) -> tuple[bool, bool] | None:
    evidence = corner.get("evidence") or {}
    devices = evidence.get("device_quantities") or {}
    if not devices:
        return None
    before, after = classification(devices)
    historical = evidence.get("device_status")
    if historical:
        for role in DEVICE_ROLES:
            if historical.get(role) != before[role]:
                raise RuntimeError(
                    f"v1 replay differs from frozen evidence: {benchmark}/{design}/{role}: "
                    f"{historical.get(role)} != {before[role]}"
                )
    corner_id = corner.get("corner_id", "tt__nominal")
    for role in DEVICE_ROLES:
        counter[(benchmark, design, method, policy, corner_id, role,
                 transition(before[role], after[role]))] += 1
    return all_valid(before), all_valid(after)


def replay_stop(corners: list[dict[str, Any]], *, use_v2: bool) -> tuple[str, str, str] | None:
    by_corner = {corner["corner_id"]: corner for corner in corners}
    for corner_id in STATIC_WORST_FIRST_ORDER:
        corner = by_corner[corner_id]
        components = dict(corner["constraint_components"])
        if use_v2:
            _, after = classification(corner["evidence"]["device_quantities"])
            components["operating_region"] = 0.0 if all_valid(after) else 1.0
        for stage in ("op", "ac", "transient"):
            for name in STAGE_COMPONENTS[stage]:
                if float(components[name]) > 0:
                    return corner_id, stage, name
    return None


def write_csv(path: Path, fields: tuple[str, ...], items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(items)


def main() -> None:
    T95.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    records = Counter()
    nominal_unique = defaultdict(dict)
    historical_failures = Counter()
    counterfactual_failures = Counter()
    corner_region_transitions = Counter()
    full_matrices = []
    stop_changes = Counter()

    for design, path in (
        ("calibration", BASE / "results/calibration/calibration.csv"),
        ("smoke", BASE / "results/smoke/evaluations.csv"),
        ("formal", BASE / "results/formal/evaluations.csv"),
    ):
        for row in rows(path):
            devices = json.loads(row["device_quantities"])
            if not devices:
                continue
            status = json.loads(row["device_status"])
            replay = classify_corner(
                {"evidence": {"device_quantities": devices, "device_status": status}},
                benchmark="task7", design=design, method=row.get("method") or "sobol",
                policy="full", counter=counts,
            )
            if replay is None:
                continue
            v1, v2 = replay
            components = json.loads(row["constraint_components"]) if row.get("constraint_components") else {}
            if components:
                old = truth(row["is_feasible"])
                new = v2 and other_constraints_pass(components)
                records[("task7", design, "full", "v1_feasible")] += int(old)
                records[("task7", design, "full", "v2_feasible")] += int(new)
                records[("task7", design, "full", "classified")] += 1
                if row.get("parameters"):
                    nominal_unique[candidate_key(row["parameters"])]["task7_" + design] = (old, new)

    for design in ("smoke", "equal_candidate", "equal_simulation_time"):
        path = BASE / f"task8/results/{design}/evaluations.csv"
        for row in rows(path):
            evidence = json.loads(row["evidence"])
            replay = classify_corner(
                {"evidence": evidence}, benchmark="task8", design=design,
                method=row["method"], policy=row["policy"], counter=counts,
            )
            if replay is None:
                continue
            _, v2 = replay
            complete_nominal = (
                row["policy"] == "full"
                or (int(row["ac_calls"]) > 0 and int(row["transient_calls"]) > 0)
            )
            if complete_nominal:
                components = json.loads(row["constraint_components"])
                old = truth(row["is_feasible"])
                new = v2 and other_constraints_pass(components)
                records[("task8", design, row["policy"], "classified")] += 1
                records[("task8", design, row["policy"], "v1_feasible")] += int(old)
                records[("task8", design, row["policy"], "v2_feasible")] += int(new)
                nominal_unique[candidate_key(row["parameters"])]["task8_" + design] = (old, new)

    for design in ("nominal_gap", "calibration", "smoke", "equal_candidate", "equal_simulation_time"):
        if design in ("nominal_gap", "calibration"):
            path = T9 / ("nominal_gap/full_pvt_matrix.jsonl" if design == "nominal_gap"
                         else "calibration/full_pvt/full_pvt_matrix.jsonl")
            iterator = json_lines(path)
        else:
            path = T9 / f"results/{design}/evaluations.csv"
            if not path.exists():
                path = path.with_suffix(".csv.gz")
            iterator = rows(path)
        for row in iterator:
            if design in ("nominal_gap", "calibration"):
                corners = row["corners"]
                policy = "full"
                method = "saved_nominal" if design == "nominal_gap" else "sobol"
                historical_pvt = truth(row["pvt_feasible"])
            else:
                corners = json.loads(row["corner_results"])
                policy, method = row["policy"], row["method"]
                historical_pvt = truth(row["is_feasible"])
            region_pairs = []
            for corner in corners:
                replay = classify_corner(
                    corner, benchmark="task9", design=design,
                    method=method, policy=policy, counter=counts,
                )
                if replay is not None:
                    region_pairs.append((corner, replay))
                    historical_failures[(design, policy)] += int(not replay[0])
                    counterfactual_failures[(design, policy)] += int(not replay[1])
                    corner_region_transitions[(design, policy, replay[0], replay[1])] += 1
            complete_matrix = len(region_pairs) == 15 and all(
                set(corner.get("completed_analyses", ())) == {"op", "ac", "transient"}
                if design in ("equal_candidate", "equal_simulation_time", "smoke")
                else True
                for corner, _ in region_pairs
            )
            if (policy == "full" and complete_matrix
                    and (design in ("nominal_gap", "calibration")
                         or row.get("simulation_status") == "success")):
                counterfactual_pvt = all(
                    replay[1] and other_constraints_pass(corner["constraint_components"])
                    for corner, replay in region_pairs
                )
                records[("task9", design, "full", "complete_matrices")] += 1
                records[("task9", design, "full", "v1_feasible")] += int(historical_pvt)
                records[("task9", design, "full", "v2_feasible")] += int(counterfactual_pvt)
                old_stop = replay_stop(corners, use_v2=False)
                new_stop = replay_stop(corners, use_v2=True)
                if old_stop != new_stop:
                    stop_changes[(design, old_stop, new_stop)] += 1
                full_matrices.append({
                    "design": design, "method": method,
                    "candidate_key": candidate_key(row["parameters"]),
                    "v1_pvt_feasible": historical_pvt,
                    "v2_pvt_feasible": counterfactual_pvt,
                    "v1_static_stop": "" if old_stop is None else "/".join(old_stop),
                    "v2_static_stop": "" if new_stop is None else "/".join(new_stop),
                    "region_invalid_corners_v1": sum(not item[1][0] for item in region_pairs),
                    "region_invalid_corners_v2": sum(not item[1][1] for item in region_pairs),
                })

    grouped = [
        {"benchmark": task, "design": design, "method": method,
         "policy": policy, "corner_id": corner, "role": role,
         "transition": change, "count": count}
        for (task, design, method, policy, corner, role, change), count in sorted(counts.items())
    ]
    write_csv(T95 / "device_classification_transitions.csv",
              ("benchmark", "design", "method", "policy", "corner_id", "role", "transition", "count"), grouped)
    write_csv(T95 / "full_matrix_counterfactual.csv",
              tuple(full_matrices[0]), full_matrices)
    summary = {
        "schema_version": "task9_5_region_replay_v1",
        "v1_semantics": V1_SEMANTICS, "v2_semantics": V2_SEMANTICS,
        "v1_semantics_hash": region_semantics_hash(version=V1_SEMANTICS),
        "v2_semantics_hash": region_semantics_hash(version=V2_SEMANTICS),
        "v2_headroom_tolerance_v": V2_HEADROOM_TOLERANCE_V,
        "device_transitions": {
            name: sum(count for key, count in counts.items() if key[-1] == name)
            for name in TRANSITIONS
        },
        "records": {"/".join(key): value for key, value in sorted(records.items())},
        "nominal_unique_candidate_count": len(nominal_unique),
        "nominal_unique_v1_feasible_count": sum(
            any(old for old, _ in outcomes.values()) for outcomes in nominal_unique.values()
        ),
        "nominal_unique_v2_feasible_count": sum(
            any(new for _, new in outcomes.values()) for outcomes in nominal_unique.values()
        ),
        "nominal_unique_demoted_count": sum(
            any(old for old, _ in outcomes.values())
            and not any(new for _, new in outcomes.values())
            for outcomes in nominal_unique.values()
        ),
        "nominal_unique_promoted_count": sum(
            not any(old for old, _ in outcomes.values())
            and any(new for _, new in outcomes.values())
            for outcomes in nominal_unique.values()
        ),
        "task9_corner_region_transitions": {
            f"{design}/{policy}/{old}_to_{new}": value
            for (design, policy, old, new), value in sorted(corner_region_transitions.items())
        },
        "task9_region_invalid_corner_count_v1": {
            "/".join(key): value for key, value in sorted(historical_failures.items())
        },
        "task9_region_invalid_corner_count_v2": {
            "/".join(key): value for key, value in sorted(counterfactual_failures.items())
        },
        "full_matrix_static_rejection_point_changes": {
            design: sum(count for key, count in stop_changes.items() if key[0] == design)
            for design in ("nominal_gap", "calibration", "smoke", "equal_candidate", "equal_simulation_time")
        },
    }
    (T95 / "region_replay_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
