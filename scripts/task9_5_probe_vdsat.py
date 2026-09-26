"""Independently probe SKY130 NMOS/PMOS OP sign and VDSAT/ID semantics."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from circuitpilot.simulator import run_ngspice  # noqa: E402


PDK = ROOT / "tools/sky130/ciel/ciel/sky130/versions/026824c7969ce6f4fc9678e6ca04b0a06a596c4b/sky130A"
PRIMITIVES = PDK / "libs.ref/sky130_fd_pr/spice"
INVARIANT = PDK / "libs.tech/ngspice/parameters/invariant.spice"
OUTPUT = ROOT / "research/sky130/two_stage_ota/task9_5/region/probe"
PROCESSES = ("tt", "ss", "ff", "fs", "sf")
CONDITIONS = (("nominal", 1.8, 27), ("low_v_high_t", 1.62, 125),
              ("high_v_low_t", 1.98, -40))
QUANTITIES = ("vgs", "vds", "vth", "vdsat", "id", "gm", "gds")


def netlist(process: str, vdd: float, temperature: float) -> str:
    nfet = "m.xmn.msky130_fd_pr__nfet_01v8"
    pfet = "m.xmp.msky130_fd_pr__pfet_01v8"
    vectors = " ".join(f"@{device}[{quantity}]" for device in (nfet, pfet)
                       for quantity in QUANTITIES)
    return "\n".join((
        "* Task 9.5 independent VDSAT and ID sign probe",
        ".option scale=1u", ".param mc_mm_switch=0 mc_pr_switch=0",
        '.include "invariant.spice"',
        f'.include "sky130_fd_pr__nfet_01v8__{process}.corner.spice"',
        f'.include "sky130_fd_pr__pfet_01v8__{process}.corner.spice"',
        f".temp {temperature}", f"VDD vdd 0 DC {vdd}",
        f"VGN gn 0 DC {vdd / 2}", f"VGP gp 0 DC {vdd / 2}",
        "XMN vdd gn 0 0 sky130_fd_pr__nfet_01v8 W=1 L=0.15",
        "XMP 0 gp vdd vdd sky130_fd_pr__pfet_01v8 W=1 L=0.15",
        ".control", "set wr_singlescale", "set wr_vecnames", "op",
        f"wrdata probe.dat {vectors}", "quit", ".endc", ".end", "",
    ))


def numeric_row(path: Path) -> list[float]:
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        values = line.split()
        if values and all(_number(value) for value in values):
            return [float(value) for value in values]
    raise RuntimeError(f"no numeric probe result: {path}")


def _number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    for process in PROCESSES:
        for condition, vdd, temperature in CONDITIONS:
            with tempfile.TemporaryDirectory(prefix="circuitpilot-task95-op-") as directory:
                stage = Path(directory)
                shutil.copy2(INVARIANT, stage / "invariant.spice")
                for polarity in ("nfet", "pfet"):
                    for suffix in ("corner", "pm3"):
                        name = f"sky130_fd_pr__{polarity}_01v8__{process}.{suffix}.spice"
                        shutil.copy2(PRIMITIVES / name, stage / name)
                netlist_path = stage / "probe.cir"
                netlist_path.write_text(netlist(process, vdd, temperature), encoding="ascii")
                result = run_ngspice(netlist_path, timeout_seconds=60.0,
                                     log_path=stage / "ngspice.log")
                raw = numeric_row(stage / "probe.dat")
                if len(raw) < 1 + 2 * len(QUANTITIES):
                    raise RuntimeError(f"incomplete OP probe: {process}/{condition}: {raw}")
                raw = raw[-2 * len(QUANTITIES):]
                devices = {
                    kind: dict(zip(QUANTITIES, raw[index * len(QUANTITIES):(index + 1) * len(QUANTITIES)]))
                    for index, kind in enumerate(("nfet", "pfet"))
                }
                destination = OUTPUT / f"{process}__{condition}"
                destination.mkdir(exist_ok=True)
                for name in ("probe.cir", "probe.dat", "ngspice.log"):
                    shutil.copy2(stage / name, destination / name)
                results.append({
                    "corner_id": f"{process}__{condition}",
                    "vdd_v": vdd, "temperature_c": temperature,
                    "devices": devices, "ngspice_seconds": result.elapsed_seconds,
                    "raw_sha256": sha256((destination / "probe.dat").read_bytes()).hexdigest(),
                })
    (OUTPUT.parent / "probe_summary.json").write_text(
        json.dumps({"schema_version": "task9_5_vdsat_probe_v1", "results": results},
                   indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8",
    )
    print(f"real SKY130 OP probes: {len(results)}")


if __name__ == "__main__":
    main()
