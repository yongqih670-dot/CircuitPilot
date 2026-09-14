import ast
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_SOURCE = PROJECT_ROOT / "src" / "circuitpilot" / "experiments"


def test_research_production_code_contains_no_simulated_result_fallbacks() -> None:
    banned = re.compile(
        r"(?i)(mock|fake|placeholder|demo[ _-]*fallback|"
        r"hard[ _-]*coded[ _-]*result|random[ _-]*result|"
        r"synthetic[ _-]*result|default[ _-]*result)"
    )
    matches = []
    for source in sorted(EXPERIMENT_SOURCE.glob("*.py")):
        for line_number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if banned.search(line):
                matches.append(f"{source.name}:{line_number}:{line.strip()}")

    assert matches == []


def test_optimizer_module_has_no_physical_simulation_dependencies() -> None:
    source = EXPERIMENT_SOURCE / "optimizer.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    forbidden = {
        "circuitpilot.analysis",
        "circuitpilot.netlist",
        "circuitpilot.netlist_generator",
        "circuitpilot.parser",
        "circuitpilot.simulator",
    }
    assert imported_modules.isdisjoint(forbidden)
