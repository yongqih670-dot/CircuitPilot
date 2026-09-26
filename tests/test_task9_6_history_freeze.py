"""Task 9.6 changes must not rewrite frozen Tasks 6--9.5."""

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "research/sky130/two_stage_ota/task9_6/history_freeze.json"


def test_task6_to_task9_5_history_stays_byte_identical():
    inventory = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert inventory["file_count"] >= 1000
    assert {row["task"] for row in inventory["files"]} >= {
        "task6", "task7", "task8", "task9", "task9_5"
    }
    for row in inventory["files"]:
        contents = (ROOT / row["path"]).read_bytes()
        assert len(contents) == row["bytes"], row["path"]
        assert sha256(contents).hexdigest() == row["sha256"], row["path"]
    digest = sha256(json.dumps(inventory["files"], sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
    assert digest == inventory["inventory_sha256"]
