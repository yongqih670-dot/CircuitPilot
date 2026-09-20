"""Audit real SKY130 process sections plus voltage/temperature execution.

This script is deliberately independent of the frozen Task 7 configuration
types, which correctly reject non-TT/non-nominal conditions.  It copies only
the content-locked primitive fragments into an ASCII temporary directory and
runs one real ngspice operating point per proposed process/V/T combination.
"""

from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from circuitpilot.simulator import resolve_ngspice_executable, run_ngspice  # noqa: E402


PDK_COMMIT = "026824c7969ce6f4fc9678e6ca04b0a06a596c4b"
PDK_ROOT = (
    PROJECT_ROOT
    / "tools"
    / "sky130"
    / "ciel"
    / "ciel"
    / "sky130"
    / "versions"
    / PDK_COMMIT
    / "sky130A"
)
LIBRARY = PDK_ROOT / "libs.tech" / "ngspice" / "sky130.lib.spice"
PRIMITIVE_ROOT = PDK_ROOT / "libs.ref" / "sky130_fd_pr" / "spice"
INVARIANT = PDK_ROOT / "libs.tech" / "ngspice" / "parameters" / "invariant.spice"
OUTPUT_ROOT = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task9" / "capability"
PROCESS_CORNERS = ("tt", "ss", "ff", "fs", "sf")
VT_CONDITIONS = (
    ("nominal", 1.80, 27.0),
    ("low_v_high_t", 1.62, 125.0),
    ("high_v_low_t", 1.98, -40.0),
)
SECTION_PATTERN = re.compile(r"^\s*\.lib\s+([^\s]+)\s*$", re.IGNORECASE)
TEMPERATURE_PATTERN = re.compile(r"Doing analysis at TEMP\s*=\s*([-+0-9.eE]+)")


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_tree_sha256() -> tuple[str, int]:
    trees = (
        PDK_ROOT / "libs.tech" / "ngspice",
        PDK_ROOT / "libs.ref" / "sky130_fd_pr" / "spice",
    )
    files: list[tuple[str, Path]] = []
    for tree in trees:
        prefix = tree.relative_to(PDK_ROOT).as_posix()
        for source in tree.rglob("*"):
            if source.is_file():
                files.append((f"{prefix}/{source.relative_to(tree).as_posix()}", source))
    files.sort(key=lambda item: item[0])
    digest = sha256()
    for relative, source in files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(source).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest(), len(files)


def discovered_sections() -> list[str]:
    sections: list[str] = []
    for line in LIBRARY.read_text(encoding="utf-8").splitlines():
        match = SECTION_PATTERN.match(line)
        if match:
            sections.append(match.group(1))
    return sections


def numeric_row(path: Path) -> list[float]:
    for raw in reversed(path.read_text(encoding="utf-8").splitlines()):
        tokens = raw.split()
        if not tokens:
            continue
        try:
            return [float(token.replace("D", "E").replace("d", "e")) for token in tokens]
        except ValueError:
            continue
    raise RuntimeError(f"no numeric row in {path}")


def probe(process: str, condition: str, vdd: float, temperature: float) -> dict[str, Any]:
    output_dir = OUTPUT_ROOT / "raw" / f"{process}__{condition}"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cp-t9-pvt-") as temporary:
        stage = Path(temporary)
        shutil.copy2(INVARIANT, stage / "invariant.spice")
        copied: list[Path] = []
        for polarity in ("nfet", "pfet"):
            for suffix in ("corner", "pm3"):
                name = f"sky130_fd_pr__{polarity}_01v8__{process}.{suffix}.spice"
                source = PRIMITIVE_ROOT / name
                if not source.is_file():
                    raise FileNotFoundError(source)
                destination = stage / name
                shutil.copy2(source, destination)
                copied.append(source)

        result_path = stage / "probe.dat"
        log_path = stage / "ngspice.log"
        netlist_path = stage / "probe.cir"
        netlist = "\n".join(
            (
                "* CircuitPilot Task 9 PVT capability probe",
                ".option scale=1u",
                ".param mc_mm_switch=0 mc_pr_switch=0",
                '.include "invariant.spice"',
                f'.include "sky130_fd_pr__nfet_01v8__{process}.corner.spice"',
                f'.include "sky130_fd_pr__pfet_01v8__{process}.corner.spice"',
                f".temp {temperature:.12g}",
                f"VDD vdd 0 DC {vdd:.12g}",
                "VGN gn 0 DC 0.9",
                "VGP gp 0 DC 0.9",
                "XMN vdd gn 0 0 sky130_fd_pr__nfet_01v8 W=1 L=0.15",
                "XMP 0 gp vdd vdd sky130_fd_pr__pfet_01v8 W=1 L=0.15",
                ".control",
                "set wr_singlescale",
                "set wr_vecnames",
                "op",
                "wrdata probe.dat v(vdd) i(VDD) "
                "@m.xmn.msky130_fd_pr__nfet_01v8[vth] "
                "@m.xmn.msky130_fd_pr__nfet_01v8[gm] "
                "@m.xmp.msky130_fd_pr__pfet_01v8[vth] "
                "@m.xmp.msky130_fd_pr__pfet_01v8[gm]",
                "quit",
                ".endc",
                ".end",
                "",
            )
        )
        netlist_path.write_text(netlist, encoding="ascii")
        simulation = run_ngspice(netlist_path, timeout_seconds=60.0, log_path=log_path)
        row = numeric_row(result_path)
        if len(row) < 6:
            raise RuntimeError(f"unexpected probe output: {row}")
        measured = row[-6:]
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        temperature_match = TEMPERATURE_PATTERN.search(log_text)
        if temperature_match is None:
            raise RuntimeError(f"ngspice did not report its execution temperature: {log_path}")
        reported_temperature = float(temperature_match.group(1))
        shutil.copy2(netlist_path, output_dir / "probe.cir")
        shutil.copy2(result_path, output_dir / "probe.dat")
        shutil.copy2(log_path, output_dir / "ngspice.log")
        return {
            "corner_id": f"{process}__{condition}",
            "process_corner": process,
            "condition": condition,
            "requested_vdd_v": vdd,
            "measured_vdd_v": measured[0],
            "requested_temperature_c": temperature,
            "reported_temperature_c": reported_temperature,
            "nfet_vth_v": measured[2],
            "nfet_gm_s": measured[3],
            "pfet_vth_v": measured[4],
            "pfet_gm_s": measured[5],
            "supply_current_a": measured[1],
            "ngspice_elapsed_seconds": simulation.elapsed_seconds,
            "returncode": simulation.returncode,
            "evidence_directory": output_dir.relative_to(PROJECT_ROOT).as_posix(),
            "nfet_corner_sha256": file_sha256(copied[0]),
            "nfet_pm3_sha256": file_sha256(copied[1]),
            "pfet_corner_sha256": file_sha256(copied[2]),
            "pfet_pm3_sha256": file_sha256(copied[3]),
        }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    sections = discovered_sections()
    missing = [corner for corner in PROCESS_CORNERS if corner not in sections]
    if missing:
        raise RuntimeError(f"required real sections absent: {missing}")
    executable = resolve_ngspice_executable()
    if executable is None:
        raise RuntimeError("ngspice executable not found")
    results = [
        probe(process, condition, vdd, temperature)
        for process in PROCESS_CORNERS
        for condition, vdd, temperature in VT_CONDITIONS
    ]
    for result in results:
        if abs(result["measured_vdd_v"] - result["requested_vdd_v"]) > 1e-9:
            raise RuntimeError(f"VDD was not applied: {result}")
        if abs(result["reported_temperature_c"] - result["requested_temperature_c"]) > 1e-9:
            raise RuntimeError(f"temperature was not applied: {result}")
    tree_hash, tree_file_count = model_tree_sha256()
    manifest = {
        "schema_version": "task9_pvt_capability_audit_v1",
        "pdk_commit": PDK_COMMIT,
        "pdk_release": "1.0.606",
        "primitive_commit": "403964dc7f9cca5ec1a8cc7b4f2a6f532b781676",
        "provenance": "FOSSi Foundation Ciel/Open_PDKs prebuilt SKY130A",
        "library": str(LIBRARY),
        "library_sha256": file_sha256(LIBRARY),
        "model_tree_sha256": tree_hash,
        "model_tree_file_count": tree_file_count,
        "ngspice_executable": executable,
        "discovered_sections": sections,
        "verified_process_corners": list(PROCESS_CORNERS),
        "verified_vt_conditions": [
            {"condition": name, "vdd_v": vdd, "temperature_c": temperature}
            for name, vdd, temperature in VT_CONDITIONS
        ],
        "all_probes_passed": all(result["returncode"] == 0 for result in results),
        "results": results,
    }
    json_path = OUTPUT_ROOT / "capability_audit.json"
    json_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_path = OUTPUT_ROOT / "capability_probes.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "probes": len(results), "passed": manifest["all_probes_passed"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
