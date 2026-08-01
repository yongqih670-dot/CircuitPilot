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
