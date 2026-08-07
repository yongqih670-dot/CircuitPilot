from pathlib import Path
import subprocess
import sys


def test_clean_environment_script_help_is_runnable() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "clean_environment_test.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0
    assert "fresh venv" in completed.stdout


def test_research_lock_pins_every_dependency_exactly() -> None:
    lock = Path(__file__).resolve().parents[1] / "requirements-research.lock"
    requirements = [
        line.strip()
        for line in lock.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert requirements
    assert all("==" in requirement for requirement in requirements)
    assert any(requirement.lower().startswith("numpy==") for requirement in requirements)
    assert any(requirement.lower().startswith("scipy==") for requirement in requirements)
    assert any(requirement.lower().startswith("optuna==") for requirement in requirements)
    assert any(requirement.lower().startswith("pyyaml==") for requirement in requirements)
    assert any(requirement.lower().startswith("pytest==") for requirement in requirements)
