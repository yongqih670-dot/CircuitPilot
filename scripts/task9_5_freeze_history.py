"""Record byte identities of frozen Task 6--9 tracked evidence before audit."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/sky130/two_stage_ota/task9_5/history_freeze.json"
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
T6 = "research/sky130/differential_amplifier/task6/"
T7 = "research/sky130/two_stage_ota/"
T8 = "research/sky130/two_stage_ota/task8/"
T9 = "research/sky130/two_stage_ota/task9/"


def task_for(path: str) -> str | None:
    if path.startswith(T6):
        return "task6"
    if path.startswith(T9):
        return "task9"
    if path.startswith(T8):
        return "task8"
    if path.startswith(T7):
        return "task7"
    if path in SOURCE_FILES:
        return "source"
    return None


def main() -> None:
    commit = subprocess.check_output([GIT, "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    names = subprocess.check_output([GIT, "ls-tree", "-r", "--name-only", "-z", "HEAD"], cwd=ROOT)
    entries = []
    for encoded in names.split(b"\0"):
        if not encoded:
            continue
        name = encoded.decode("utf-8")
        task = task_for(name)
        if task is None:
            continue
        path = ROOT / name
        if not path.is_file():
            raise RuntimeError(f"missing historical file: {name}")
        data = path.read_bytes()
        entries.append({"path": name, "task": task, "bytes": len(data), "sha256": sha256(data).hexdigest()})
    entries.sort(key=lambda item: item["path"])
    digest = sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {"schema_version": "task9_5_history_freeze_v1", "parent_commit": commit,
             "file_count": len(entries), "inventory_sha256": digest, "files": entries},
            indent=2, sort_keys=True,
        ) + "\n", encoding="utf-8",
    )
    print(f"frozen tracked files: {len(entries)}; inventory sha256: {digest}")


if __name__ == "__main__":
    main()
