"""Losslessly publish complete negative 45-analysis matrix in Git."""

from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_runs/task9_5_full_characterization/full_matrix.json"
TARGET = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/full_characterization_matrix.json.gz"
MANIFEST = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/full_characterization_matrix_manifest.json"


def main() -> None:
    if TARGET.exists() or MANIFEST.exists():
        raise FileExistsError("refusing to overwrite characterized matrix")
    source = SOURCE.read_bytes()
    with TARGET.open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle,
                           compresslevel=9, mtime=0) as compressed:
            compressed.write(source)
    with gzip.open(TARGET, "rb") as handle:
        assert handle.read() == source
    payload = {
        "source_sha256": sha256(source).hexdigest(),
        "source_bytes": len(source),
        "compressed_sha256": sha256(TARGET.read_bytes()).hexdigest(),
        "compressed_bytes": TARGET.stat().st_size,
        "matrix_file": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
