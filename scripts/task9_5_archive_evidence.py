"""Create independent, content-hashed historical raw-evidence archives."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "research_runs/task9_5_archives"
SOURCES = {
    "task6": ("research_runs/task6", "research_runs/task6_postfix"),
    "task7": ("research_runs/task7", "research/sky130/two_stage_ota/results"),
    "task8": ("research/sky130/two_stage_ota/task8/results",),
    "task9": ("research/sky130/two_stage_ota/task9/results",),
    "task9_5": ("research_runs/task9_5_feasibility",),
    "task9_5_full": ("research_runs/task9_5_full_characterization",),
}


def digest(path: Path) -> str:
    hash_value = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hash_value.update(chunk)
    return hash_value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=SOURCES)
    args = parser.parse_args()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    target = DESTINATION / f"{args.task}_raw_evidence.zip"
    manifest = DESTINATION / f"{args.task}_archive_manifest.json"
    if target.exists() or manifest.exists():
        raise FileExistsError("refusing to overwrite an existing evidence archive")
    files = sorted(
        file for source in SOURCES[args.task]
        for file in (ROOT / source).rglob("*") if file.is_file()
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     text=True).strip()
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z", "--", *SOURCES[args.task]], cwd=ROOT,
    ).decode("utf-8", errors="surrogateescape").split("\0"))
    bytes_total = 0
    tracked_count = 0
    with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=4,
                 allowZip64=True) as archive:
        for index, file in enumerate(files, 1):
            relative = file.relative_to(ROOT).as_posix()
            entry = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry._compresslevel = 4
            with file.open("rb") as source, archive.open(entry, "w") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            bytes_total += file.stat().st_size
            tracked_count += relative in tracked
            if index % 25000 == 0:
                print(f"{args.task}: {index}/{len(files)} files", flush=True)
    result = {
        "task": args.task,
        "source_roots": list(SOURCES[args.task]),
        "associated_commit": commit,
        "archive_path": str(target.relative_to(ROOT)).replace("\\", "/"),
        "archive_sha256": digest(target),
        "archive_bytes": target.stat().st_size,
        "source_files": len(files),
        "source_bytes": bytes_total,
        "git_tracked_source_files": tracked_count,
        "local_only_source_files": len(files) - tracked_count,
        "generation_command": f"python scripts/task9_5_archive_evidence.py {args.task}",
    }
    manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
