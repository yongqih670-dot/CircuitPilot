"""Five-corner v2 OP plus diagnostic AC/transient, never Full-PVT."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.task9_evaluator import execute_real_pvt_stage
from circuitpilot.sky130_pvt import task9_corner_config, task9_runtime_paths
from circuitpilot.sky130_two_stage_ota import (
    DEVICE_ROLES, PFET_ROLES, _numeric_rows, generate_task7_op_netlist,
    parse_task7_operating_point,
)
from circuitpilot.task9_protocol import CORNER_BY_ID, CANONICAL_CORNER_ORDER
from circuitpilot.task9_6_budget import BudgetLedger
from circuitpilot.task9_6_device_coordinates import preserve_device_coordinates
from circuitpilot.task9_6_v2_evaluator import (
    FROZEN_TASK7_CONFIG, evaluate_task9_6_benchmark_v2_candidate,
)


def diagnostic_op_netlist(base: str, output_path: str, config: Any) -> str:
    vectors = ["v(mirror)", "i(VDD)"]
    for index, role in enumerate(DEVICE_ROLES, start=1):
        name = config.pfet_device_name if role in PFET_ROLES else config.nfet_device_name
        vectors.append(f"@m.xm{index}.m{name}[id]")
    marker = "quit\n.endc"
    if base.count(marker) != 1:
        raise ValueError("unexpected Task 7 OP netlist control structure")
    return base.replace(marker, f"wrdata {output_path} {' '.join(vectors)}\n{marker}")


def run_diagnostic_op(*, parameters: Mapping[str, float | int], corner_id: str,
                      directory: Path, executable: str, ledger: BudgetLedger,
                      activity: str, candidate_id: str) -> dict[str, Any]:
    """Separate budgeted OP probe; preserve both terminal and internal signs."""
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    base = frozen.circuit_config
    if corner_id not in CORNER_BY_ID:
        raise ValueError("unknown frozen Task 9 corner")
    config = task9_corner_config(base, CORNER_BY_ID[corner_id])
    with task9_runtime_paths(base.model, CORNER_BY_ID[corner_id].process_corner,
                             directory) as paths:
        extra = str(Path(paths.runtime_netlist).with_name("diagnostic_op.dat")).replace("\\", "/")
        text = generate_task7_op_netlist(
            config, parameters, invariant_path=paths.runtime_invariant,
            nfet_corner_path=paths.runtime_corner,
            pfet_corner_path=paths.runtime_pfet_corner,
            op_output_path=paths.runtime_op, device_op_output_path=paths.runtime_device,
        )
        Path(paths.runtime_netlist).write_text(
            diagnostic_op_netlist(text, extra, config), encoding="utf-8")
        process = ledger.run(activity, candidate_id, paths.runtime_netlist,
                             executable=executable, timeout_seconds=frozen.timeout,
                             log_path=paths.runtime_log, preserve_runtime_paths=True)
        operating = parse_task7_operating_point(paths.runtime_op, paths.runtime_device)
        row = _numeric_rows(extra)[-1]
        if len(row) < 2 + len(DEVICE_ROLES):
            raise ValueError("diagnostic Id/mirror output incomplete")
        mirror_v, supply_current_raw_a, *ids = row[-(2 + len(DEVICE_ROLES)):]
        nodes = {
            "gnd": 0.0, "vdd": operating.supply_voltage_v,
            "vin_plus": operating.input_positive_voltage_v,
            "vin_minus": operating.input_negative_voltage_v,
            "stage1_out": operating.stage1_voltage_v,
            "vout": operating.output_voltage_v,
            "tail": operating.tail_voltage_v,
            "tail_bias": operating.tail_bias_v,
            "second_load_bias": operating.second_load_bias_v,
            "mirror": mirror_v,
        }
        devices = {
            role: preserve_device_coordinates(role, nodes,
                                              operating.device_quantities[role],
                                              model_id_raw_a=ids[index])
            for index, role in enumerate(DEVICE_ROLES)
        }
        return {
            "schema_version": "task9_6_diagnostic_op_v1",
            "corner_id": corner_id, "node_voltages_v": nodes,
            "signed_supply_current_a": supply_current_raw_a,
            "branch_current_status": "supply_source_only; internal device Id is not an external branch sensor",
            "devices": devices,
            "ngspice_elapsed_seconds": process.elapsed_seconds,
            "process_status": "success",
        }


def evaluate_task9_6_v2_local_diagnostic(
    *, parameters: Mapping[str, float | int], corner_ids: Sequence[str],
    evaluation_directory: Path, executable: str, ledger: BudgetLedger,
    activity: str, candidate_id: str,
) -> dict[str, Any]:
    """Run exactly five v2 OP + ten stage measurements + five extra OP.

    AC/transient reuse only Task 9's physical stage measurement function,
    never its historical v1 robust result or operating-region classification.
    """
    if len(corner_ids) != 5 or len(set(corner_ids)) != 5 or not set(corner_ids) <= set(CANONICAL_CORNER_ORDER):
        raise ValueError("local diagnostic requires five distinct frozen corners")
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    with ledger.meter(activity, candidate_id):
        v2_op = evaluate_task9_6_benchmark_v2_candidate(
            parameters=parameters, evaluation_directory=evaluation_directory / "v2_op",
            executable=executable, mode="op_only", corners=corner_ids)
    if v2_op["robust_feedback"]["exact_robust_violation"] is not None:
        raise RuntimeError("local diagnostic cannot have a Full-PVT exact result")
    by_id = {item["corner_id"]: item for item in v2_op["raw_v2_result"]["corners"]}
    rows = []
    for corner_id in corner_ids:
        stages = {}
        for kind in ("ac", "transient"):
            with ledger.meter(activity, candidate_id):
                measured = execute_real_pvt_stage(
                    kind, base_config=frozen.circuit_config,
                    corner_id=corner_id, parameters=parameters,
                    directory=evaluation_directory / corner_id / kind,
                    executable=executable, timeout_seconds=frozen.timeout,
                    start_frequency_hz=frozen.ngspice_config.start_frequency_hz,
                    stop_frequency_hz=frozen.ngspice_config.stop_frequency_hz,
                    points_per_decade=frozen.ngspice_config.points_per_decade)
            stages[kind] = {
                "metrics": measured.metrics, "statuses": measured.statuses,
                "error": measured.error,
                "reported_temperature_c": measured.reported_temperature_c,
                "process_elapsed_seconds": measured.process_elapsed_seconds,
            }
        try:
            probe = run_diagnostic_op(
                parameters=parameters, corner_id=corner_id,
                directory=evaluation_directory / corner_id / "diagnostic_op",
                executable=executable, ledger=ledger, activity=activity,
                candidate_id=candidate_id)
        except Exception as exc:
            probe = {"process_status": "error", "error": f"{type(exc).__name__}: {exc}"}
        rows.append({"corner_id": corner_id, "v2_op": by_id[corner_id],
                     "ac": stages["ac"], "transient": stages["transient"],
                     "diagnostic_op": probe})
    return {
        "schema_version": "task9_6_v2_five_corner_diagnostic_v1",
        "benchmark_v2_hash": v2_op["benchmark_v2_hash"],
        "robust_evaluation_status": "partial",
        "exact_robust_violation": None,
        "corner_ids": list(corner_ids),
        "parameters": dict(parameters), "v2_op_wrapper": v2_op,
        "corners": rows,
    }
