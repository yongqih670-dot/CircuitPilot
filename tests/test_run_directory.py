import json
from pathlib import Path
import re

import pytest

from circuitpilot.exceptions import RunDirectoryError
from circuitpilot.run_directory import (
    RUN_CONTEXT_FILENAME,
    generate_run_id,
    prepare_research_run_directory,
    snapshot_run_input_config,
)


def test_default_directory_uses_unique_run_id(tmp_path: Path) -> None:
    first = prepare_research_run_directory(None, default_root=tmp_path / "output")
    second = prepare_research_run_directory(None, default_root=tmp_path / "output")

    assert first.run_id != second.run_id
    assert first.path.name == first.run_id
    assert second.path.name == second.run_id
    assert re.fullmatch(r"cp-\d{8}T\d{12}Z-[0-9a-f]{12}", first.run_id)
    assert (first.path / RUN_CONTEXT_FILENAME).is_file()


def test_nonempty_directory_requires_explicit_resume(tmp_path: Path) -> None:
    destination = tmp_path / "research_run"
    first = prepare_research_run_directory(destination)
    (destination / "partial.log").write_text("partial\n", encoding="utf-8")

    with pytest.raises(RunDirectoryError, match="not empty"):
        prepare_research_run_directory(destination)

    resumed = prepare_research_run_directory(destination, resume=True)
    context = json.loads(
        (destination / RUN_CONTEXT_FILENAME).read_text(encoding="utf-8")
    )
    assert resumed.run_id == first.run_id
    assert resumed.resumed
    assert resumed.resume_count == 1
    assert context["resume_count"] == 1


def test_resume_rejects_arbitrary_or_empty_directory(tmp_path: Path) -> None:
    arbitrary = tmp_path / "arbitrary"
    arbitrary.mkdir()
    (arbitrary / "unrelated.txt").write_text("data", encoding="utf-8")
    with pytest.raises(RunDirectoryError, match="missing run_context.json"):
        prepare_research_run_directory(arbitrary, resume=True)

    with pytest.raises(RunDirectoryError, match="cannot resume empty"):
        prepare_research_run_directory(tmp_path / "empty", resume=True)


def test_resume_requires_original_yaml_bytes(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("value: 1\n", encoding="utf-8")
    run = prepare_research_run_directory(tmp_path / "run")
    snapshot_run_input_config(run, config)
    config.write_text("value: 2\n", encoding="utf-8")
    with pytest.raises(RunDirectoryError, match="does not match"):
        prepare_research_run_directory(
            run.path,
            resume=True,
            source_config=config,
        )
    context = json.loads(
        (run.path / RUN_CONTEXT_FILENAME).read_text(encoding="utf-8")
    )
    assert context["resume_count"] == 0


def test_resume_requires_same_resolved_configuration(tmp_path: Path) -> None:
    original_hash = "a" * 64
    run = prepare_research_run_directory(
        tmp_path / "run",
        configuration_sha256=original_hash,
    )
    with pytest.raises(RunDirectoryError, match="resolved configuration"):
        prepare_research_run_directory(
            run.path,
            resume=True,
            configuration_sha256="b" * 64,
        )


def test_resume_requires_explicit_output_directory() -> None:
    with pytest.raises(RunDirectoryError, match="requires an explicit"):
        prepare_research_run_directory(None, resume=True)


def test_generated_run_ids_are_distinct() -> None:
    assert generate_run_id() != generate_run_id()
