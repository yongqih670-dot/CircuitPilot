"""Durable, fail-closed per-process Task 9.6 Phase-B simulator budget."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Iterator

from circuitpilot.experiments import task9_evaluator
from circuitpilot.simulator import run_ngspice as unmetered_run_ngspice


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "research/sky130/two_stage_ota/task9_6/execution_plan.json"
AUTHORIZATION = ROOT / "research/sky130/two_stage_ota/task9_6/phase_b_authorization.json"
FROZEN_PLAN_SHA256 = "aa0bb79380e4f22b5e11b03acc13cf0b04a9edfe4dd47e2271f45272c501ee90"
SECONDS_SAFETY_RESERVE = 5.0


class BudgetExhausted(RuntimeError):
    """A frozen allocation or global process/time/wall limit is reached."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BudgetLedger:
    """Append and fsync start/end events; orphan starts cost their full timeout."""

    def __init__(self, path: Path, *, plan_path: Path = PLAN,
                 authorization_path: Path = AUTHORIZATION) -> None:
        self.path = path
        data = plan_path.read_bytes()
        if sha256(data).hexdigest() != FROZEN_PLAN_SHA256:
            raise ValueError("frozen Task 9.6 Phase-B plan content changed")
        self.plan = json.loads(data)
        approval = json.loads(authorization_path.read_text(encoding="utf-8"))
        if (approval.get("schema_version") != "task9_6_phase_b_authorization_v1"
                or approval.get("approved") is not True
                or approval.get("plan_sha256") != FROZEN_PLAN_SHA256
                or self.plan.get("phase_b_approved") is not False):
            raise ValueError("separate explicit Phase-B authorization is absent or invalid")
        self.events = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.events.append(json.loads(line))
        self._reconcile()

    def _reconcile(self) -> None:
        starts: dict[int, dict[str, Any]] = {}
        finishes: dict[int, dict[str, Any]] = {}
        for event in self.events:
            if event.get("type") == "start":
                sequence = event["sequence"]
                if sequence in starts or event.get("activity") not in self.plan["activity_process_allocations"]:
                    raise ValueError("invalid or duplicate budget-ledger process start")
                starts[sequence] = event
            elif event.get("type") == "finish":
                sequence = event["sequence"]
                if sequence in finishes:
                    raise ValueError("duplicate budget-ledger process finish")
                finishes[sequence] = event
            else:
                raise ValueError("unknown budget-ledger event")
        if set(finishes) - set(starts) or set(starts) != set(range(1, len(starts) + 1)):
            raise ValueError("budget-ledger sequence is incomplete or out of order")
        self.starts = starts
        self.finishes = finishes
        self.process_count = len(starts)
        self.activity_counts = {name: 0 for name in self.plan["activity_process_allocations"]}
        for event in starts.values():
            self.activity_counts[event["activity"]] += 1
        self.simulator_seconds = sum(
            max(0.0, float(finishes[seq]["charged_seconds"])) if seq in finishes
            else float(start["reserved_timeout_seconds"])
            for seq, start in starts.items()
        )
        self.first_start_utc = (datetime.fromisoformat(starts[1]["timestamp_utc"])
                                if starts else None)

    def _append(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.events.append(event)
        self._reconcile()

    def remaining(self, activity: str) -> dict[str, float | int]:
        if activity not in self.activity_counts:
            raise ValueError(f"unregistered Phase-B activity: {activity}")
        limits = self.plan["global_limits"]
        elapsed_wall = (0.0 if self.first_start_utc is None else
                        max(0.0, (_utc_now() - self.first_start_utc).total_seconds()))
        return {
            "activity_processes": self.plan["activity_process_allocations"][activity]
            - self.activity_counts[activity],
            "global_processes": limits["maximum_ngspice_processes"] - self.process_count,
            "simulator_seconds": limits["maximum_accumulated_simulator_seconds"]
            - self.simulator_seconds,
            "wall_seconds": limits["maximum_wall_seconds"] - elapsed_wall,
        }

    def require_capacity(self, activity: str, *, processes: int = 1) -> None:
        available = self.remaining(activity)
        if (min(available["activity_processes"], available["global_processes"]) < processes
                or available["simulator_seconds"] <= SECONDS_SAFETY_RESERVE
                or available["wall_seconds"] <= SECONDS_SAFETY_RESERVE):
            raise BudgetExhausted(f"frozen Task 9.6 budget exhausted for {activity}: {available}")

    def run(self, activity: str, candidate_id: str, netlist_path: str | Path,
            *, runner: Callable[..., Any] = unmetered_run_ngspice,
            **kwargs: Any) -> Any:
        self.require_capacity(activity)
        available = self.remaining(activity)
        requested_timeout = float(kwargs.get("timeout_seconds", 60.0))
        timeout = min(requested_timeout,
                      float(available["simulator_seconds"]) - SECONDS_SAFETY_RESERVE,
                      float(available["wall_seconds"]) - SECONDS_SAFETY_RESERVE)
        if timeout <= 0:
            raise BudgetExhausted("insufficient simulator or wall-time reserve")
        sequence = self.process_count + 1
        stamp = _utc_now().isoformat()
        self._append({
            "type": "start", "sequence": sequence, "activity": activity,
            "candidate_id": candidate_id, "timestamp_utc": stamp,
            "netlist_path": str(netlist_path), "reserved_timeout_seconds": timeout,
        })
        started = monotonic()
        try:
            outcome = runner(netlist_path, **{**kwargs, "timeout_seconds": timeout})
        except BaseException as exc:
            self._append({"type": "finish", "sequence": sequence,
                          "timestamp_utc": _utc_now().isoformat(),
                          "charged_seconds": max(0.0, monotonic() - started),
                          "elapsed_estimated": True,
                          "status": f"{type(exc).__name__}: {exc}"})
            raise
        self._append({"type": "finish", "sequence": sequence,
                      "timestamp_utc": _utc_now().isoformat(),
                      "charged_seconds": max(float(outcome.elapsed_seconds),
                                             monotonic() - started),
                      "elapsed_estimated": False, "status": "success"})
        return outcome

    @contextmanager
    def meter(self, activity: str, candidate_id: str) -> Iterator[None]:
        """Meter existing v2 evaluator's real stage call without editing history."""
        previous = task9_evaluator.run_ngspice
        if previous is not unmetered_run_ngspice:
            raise RuntimeError("nested or altered Task 9 simulator boundary")

        def metered(netlist_path: str | Path, **kwargs: Any) -> Any:
            return self.run(activity, candidate_id, netlist_path, **kwargs)

        task9_evaluator.run_ngspice = metered
        try:
            yield
        finally:
            task9_evaluator.run_ngspice = previous

    def summary(self) -> dict[str, Any]:
        return {
            "frozen_plan_sha256": FROZEN_PLAN_SHA256,
            "process_count": self.process_count,
            "activity_process_counts": dict(self.activity_counts),
            "accumulated_simulator_seconds": self.simulator_seconds,
            "first_process_utc": (self.first_start_utc.isoformat()
                                  if self.first_start_utc else None),
            "orphaned_process_starts": sorted(set(self.starts) - set(self.finishes)),
            "remaining_global": self.remaining("hierarchical_search_96_candidates"),
        }
