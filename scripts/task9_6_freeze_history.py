"""Freeze tracked Tasks 6--9.5 bytes before additive Task 9.6 work."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/sky130/two_stage_ota/task9_6/history_freeze.json"
GIT = r"C:\Program Files\Git\cmd\git.exe"
SOURCE_FILES = {
    "src/circuitpilot/task6_physics.py",
    "src/circuitpilot/task6_protocol.py",
    "src/circuitpilot/task7_protocol.py",
    "src/circuitpilot/task8_protocol.py",
    "src/circuitpilot/task9_protocol.py",
    "src/circuitpilot/sky130_two_stage_ota.py",
    "src/circuitpilot/experiments/task6_statistics.py",
    "src/circuitpilot/experiments/task8_statistics.py",
    "src/circuitpilot/experiments/task9_evaluator.py",
    "scripts/finalize_task7.py",
    "scripts/finalize_task8.py",
    "scripts/finalize_task9_statistics.py",
}


def historical_task(path: str) -> str | None:
    if path.startswith("research/sky130/two_stage_ota/task9_6/"):
        return None
    if path.startswith("research/sky130/differential_amplifier/task6/"):
        return "task6"
    if path.startswith("research/sky130/two_stage_ota/task9_5/"):
        return "task9_5"
    if path.startswith("research/sky130/two_stage_ota/task9/"):
        return "task9"
    if path.startswith("research/sky130/two_stage_ota/task8/"):
        return "task8"
    if path.startswith("research/sky130/two_stage_ota/"):
        return "task7"
    if path in SOURCE_FILES:
        return "historical_source"
    if path.startswith(("src/circuitpilot/", "scripts/", "tests/")) and (
        "task9_5" in Path(path).name
    ):
        return "task9_5_source"
    return None


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to replace history freeze: {OUTPUT}")
    parent_commit = subprocess.check_output([GIT, "rev-parse", "HEAD"], cwd=ROOT,
                                            text=True).strip()
    names = subprocess.check_output([GIT, "ls-tree", "-r", "--name-only", "-z", "HEAD"], cwd=ROOT)
    entries = []
    for encoded in names.split(b"\0"):
        if not encoded:
            continue
        name = encoded.decode("utf-8")
        task = historical_task(name)
        if task is None:
            continue
        data = (ROOT / name).read_bytes()
        entries.append({"path": name, "task": task,
                        "bytes": len(data), "sha256": sha256(data).hexdigest()})
    entries.sort(key=lambda entry: entry["path"])
    inventory_sha256 = sha256(json.dumps(entries, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    prior = json.loads((ROOT / "research/sky130/two_stage_ota/task9_5/history_freeze.json")
                       .read_text(encoding="utf-8"))
    payload = {
        "schema_version": "task9_6_history_freeze_v1",
        "parent_commit": parent_commit,
        "file_count": len(entries),
        "inventory_sha256": inventory_sha256,
        "task9_5_prior_inventory_sha256": prior["inventory_sha256"],
        "files": entries,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(f"frozen {len(entries)} historical files; {inventory_sha256}")


if __name__ == "__main__":
    main()
