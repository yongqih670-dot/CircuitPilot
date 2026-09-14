"""Validate, analyze, and package accepted Research Task 6 suites."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable
import zipfile

from circuitpilot.experiments.task6_statistics import (
    load_task6_summary,
    validate_task6_fairness,
    write_task6_statistics,
)
from circuitpilot.task6_protocol import (
    FULL_POLICY,
    METHODS,
    SCREENED_POLICY,
    evaluation_policy_family_hash,
)


DESIGNS: dict[str, dict[str, Any]] = {
    "smoke": {"candidate_cap": 25, "expensive_ac_budget": None, "seeds": (0, 1, 2)},
    "formal_equal_candidate": {
        "candidate_cap": 100, "expensive_ac_budget": None,
        "seeds": tuple(range(10)),
    },
    "formal_equal_cost": {
        "candidate_cap": 300, "expensive_ac_budget": 200,
        "seeds": tuple(range(10)),
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_accepted_suites(
    suite_paths: Iterable[Path], design: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    suites, summaries = [], []
    for raw_path in suite_paths:
        path = raw_path.resolve()
        state = _read_json(path / "suite_state.json")
        if state.get("status") != "success":
            raise ValueError(f"suite is not complete: {path}")
        if state.get("design") != design:
            raise ValueError(f"suite design mismatch: {path}")
        if state.get("task6_policy_family_hash") != evaluation_policy_family_hash():
            raise ValueError(f"suite policy-family hash mismatch: {path}")
        suites.append({"path": path, "state": state})
        summaries.extend(
            load_task6_summary(cell["run_directory"])
            for cell in state["cells"].values()
        )
    protocol = DESIGNS[design]
    validate_task6_fairness(
        summaries,
        expected_methods=METHODS,
        expected_policies=(FULL_POLICY, SCREENED_POLICY),
        expected_seeds=protocol["seeds"],
        candidate_cap=protocol["candidate_cap"],
        expensive_ac_budget=protocol["expensive_ac_budget"],
        experiment_design=design,
    )
    return suites, summaries


def _copy_provenance(
    suites: list[dict[str, Any]], design_output: Path,
) -> list[dict[str, Any]]:
    provenance = design_output / "provenance"
    provenance.mkdir(parents=True, exist_ok=True)
    accepted = []
    for suite in suites:
        path, state = suite["path"], suite["state"]
        methods = tuple(str(method) for method in state["methods"])
        label = methods[0] if len(methods) == 1 else "all_methods"
        state_target = provenance / f"{label}_suite_state.json"
        fairness_target = provenance / f"{label}_fairness_validation.json"
        shutil.copyfile(path / "suite_state.json", state_target)
        shutil.copyfile(path / "fairness_validation.json", fairness_target)
        accepted.append({
            "suite_label": label, "methods": list(methods),
            "source_suite": str(path),
            "git_commit": state["git_commit"],
            "suite_state_sha256": _sha256(state_target),
            "fairness_validation_sha256": _sha256(fairness_target),
        })
    return sorted(accepted, key=lambda row: row["suite_label"])


def _archive_evidence(
    design: str, suites: list[dict[str, Any]], output: Path,
) -> list[dict[str, Any]]:
    archive_directory = output / "raw_evidence"
    archive_directory.mkdir(parents=True, exist_ok=True)
    manifest = []
    for suite in suites:
        state = suite["state"]
        for method in (str(value) for value in state["methods"]):
            for policy in (FULL_POLICY, SCREENED_POLICY):
                archive = archive_directory / f"{design}_{method}_{policy}.zip"
                run_entries = []
                with zipfile.ZipFile(
                    archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
                ) as bundle:
                    for seed in DESIGNS[design]["seeds"]:
                        key = f"{method}/{policy}/seed_{seed}"
                        cell = state["cells"][key]
                        run = Path(cell["run_directory"]).resolve()
                        file_count = 0
                        for source in sorted(
                            path for path in run.rglob("*") if path.is_file()
                        ):
                            relative = source.relative_to(run).as_posix()
                            bundle.write(source, f"seed_{seed}/{relative}")
                            file_count += 1
                        run_entries.append({
                            "seed": seed, "run_id": cell["run_id"],
                            "source_run_directory": str(run),
                            "file_count": file_count,
                        })
                manifest.append({
                    "design": design, "method": method,
                    "evaluation_policy": policy,
                    "archive": archive.relative_to(output).as_posix(),
                    "archive_size_bytes": archive.stat().st_size,
                    "archive_sha256": _sha256(archive), "runs": run_entries,
                })
    return sorted(
        manifest,
        key=lambda row: (row["design"], row["method"], row["evaluation_policy"]),
    )


def _publish_design(
    design: str, suite_paths: Iterable[Path], output: Path,
    *, archive_raw: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    suites, summaries = _load_accepted_suites(suite_paths, design)
    design_output = output / design
    design_output.mkdir(parents=True, exist_ok=False)
    write_task6_statistics(summaries, design_output / "statistics")
    accepted = _copy_provenance(suites, design_output)
    protocol = DESIGNS[design]
    fairness = validate_task6_fairness(
        summaries,
        expected_methods=METHODS,
        expected_policies=(FULL_POLICY, SCREENED_POLICY),
        expected_seeds=protocol["seeds"],
        candidate_cap=protocol["candidate_cap"],
        expensive_ac_budget=protocol["expensive_ac_budget"],
        experiment_design=design,
    )
    _write_json(design_output / "fairness_validation.json", fairness)
    _write_json(design_output / "accepted_suites.json", {
        "design": design, "accepted_suites": accepted,
    })
    evidence = _archive_evidence(design, suites, output) if archive_raw else []
    return summaries, evidence


def _write_file_hashes(output: Path) -> None:
    target = output / "file_hashes.json"
    files = [
        path for path in sorted(output.rglob("*"))
        if path.is_file() and path != target
    ]
    _write_json(target, {
        "algorithm": "sha256",
        "excludes": ["file_hashes.json"],
        "files": {
            path.relative_to(output).as_posix(): _sha256(path) for path in files
        },
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal-a-suite", action="append", type=Path, required=True)
    parser.add_argument("--formal-b-suite", action="append", type=Path, required=True)
    parser.add_argument("--smoke-suite", action="append", type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=Path("research/sky130/differential_amplifier/task6/results"),
    )
    parser.add_argument("--skip-raw-archives", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    for child in ("formal_equal_candidate", "formal_equal_cost", "combined", "smoke"):
        if (output / child).exists():
            raise FileExistsError(
                f"refusing to replace existing published results: {output / child}"
            )

    all_summaries, evidence = [], []
    formal_a, archives = _publish_design(
        "formal_equal_candidate", args.formal_a_suite, output,
        archive_raw=not args.skip_raw_archives,
    )
    all_summaries.extend(formal_a)
    evidence.extend(archives)
    formal_b, archives = _publish_design(
        "formal_equal_cost", args.formal_b_suite, output,
        archive_raw=not args.skip_raw_archives,
    )
    all_summaries.extend(formal_b)
    evidence.extend(archives)
    if args.smoke_suite:
        smoke, archives = _publish_design(
            "smoke", args.smoke_suite, output,
            archive_raw=not args.skip_raw_archives,
        )
        evidence.extend(archives)
    combined = output / "combined"
    combined.mkdir(parents=True, exist_ok=False)
    write_task6_statistics(all_summaries, combined / "statistics")
    _write_json(output / "evidence_manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "task6_policy_family_hash": evaluation_policy_family_hash(),
        "archives": evidence,
    })
    _write_file_hashes(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
