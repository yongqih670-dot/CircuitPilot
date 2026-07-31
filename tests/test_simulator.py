from pathlib import Path
import subprocess

import pytest

from circuitpilot.exceptions import SimulationError
from circuitpilot.simulator import run_ngspice


def test_run_ngspice_returns_captured_process_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    netlist = tmp_path / "filter.cir"
    netlist.write_text(".end\n", encoding="utf-8")
    monkeypatch.setattr("circuitpilot.simulator.shutil.which", lambda _: "ngspice-bin")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[:2] == ["ngspice-bin", "-b"]
        assert command[-1] == str(netlist.resolve())
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 12
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("circuitpilot.simulator.subprocess.run", fake_run)

    result = run_ngspice(netlist, timeout_seconds=12)

    assert result.returncode == 0
    assert result.stdout == "ok"
    assert result.elapsed_seconds >= 0


def test_run_ngspice_raises_for_missing_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    netlist = tmp_path / "filter.cir"
    netlist.write_text(".end\n", encoding="utf-8")
    monkeypatch.setattr("circuitpilot.simulator.shutil.which", lambda _: None)

    with pytest.raises(SimulationError, match="was not found"):
        run_ngspice(netlist, executable="missing-ngspice")


def test_run_ngspice_raises_for_nonzero_return_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    netlist = tmp_path / "filter.cir"
    netlist.write_text("bad netlist", encoding="utf-8")
    monkeypatch.setattr("circuitpilot.simulator.shutil.which", lambda _: "ngspice-bin")
    monkeypatch.setattr(
        "circuitpilot.simulator.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 2, stdout="", stderr="syntax error"
        ),
    )

    with pytest.raises(SimulationError, match="status 2.*syntax error"):
        run_ngspice(netlist)


def test_run_ngspice_wraps_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    netlist = tmp_path / "filter.cir"
    netlist.write_text(".end\n", encoding="utf-8")
    monkeypatch.setattr("circuitpilot.simulator.shutil.which", lambda _: "ngspice-bin")

    def fake_timeout(command: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(command, timeout=1)

    monkeypatch.setattr("circuitpilot.simulator.subprocess.run", fake_timeout)

    with pytest.raises(SimulationError, match="timed out"):
        run_ngspice(netlist, timeout_seconds=1)


def test_run_ngspice_rejects_missing_netlist(tmp_path: Path) -> None:
    with pytest.raises(SimulationError, match="netlist does not exist"):
        run_ngspice(tmp_path / "missing.cir")
