"""Frozen Task 6--9 tracked evidence must never be silently rewritten."""

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "research/sky130/two_stage_ota/task9_5/history_freeze.json"


def test_old_task6_to_task9_files_preserve_frozen_sha256():
    inventory = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert inventory["file_count"] >= 900
    assert {row["task"] for row in inventory["files"]} >= {
        "task6", "task7", "task8", "task9"
    }
    for row in inventory["files"]:
        contents = (ROOT / row["path"]).read_bytes()
        assert len(contents) == row["bytes"], row["path"]
        assert sha256(contents).hexdigest() == row["sha256"], row["path"]
    digest = sha256(json.dumps(inventory["files"], sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
    assert digest == inventory["inventory_sha256"]
