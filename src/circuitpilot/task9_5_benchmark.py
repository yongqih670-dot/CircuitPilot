"""Additive Task 9 benchmark-v2 identity for corrected region semantics."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from circuitpilot.task9_protocol import (
    CORNER_ORDER_HASH, CORNER_SUITE_HASH, PVT_BENCHMARK_HASH, TASK9_PROTOCOL_HASH,
)
from circuitpilot.task9_5_region import V2_SEMANTICS, region_semantics_hash


PHASE_MARGIN_SEMANTICS = "task7_unwrapped_phase_at_same_first_ugf_v1"
TASK7_SEARCH_SPACE_HASH = "36e72bd54d2b1850af1ce1c8a69dbe7de22f552d49713edfbb0d3de83cd4f6db"
SELECTED_SPECIFICATION_HASH = "05b5c71863b852dc758cfed7643ace6aa9f6a7636856bf1eb09addef77681748"


def benchmark_v2_definition(*, region_version: str = V2_SEMANTICS,
                            phase_margin_version: str = PHASE_MARGIN_SEMANTICS) -> dict[str, Any]:
    return {
        "schema_version": "task9_5_semantics_only_benchmark_v2",
        "parent_task9_pvt_benchmark_hash": PVT_BENCHMARK_HASH,
        "parent_task9_protocol_hash": TASK9_PROTOCOL_HASH,
        "corner_suite_hash": CORNER_SUITE_HASH,
        "corner_order_hash": CORNER_ORDER_HASH,
        "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
        "selected_specification_hash": SELECTED_SPECIFICATION_HASH,
        "region_semantics_version": region_version,
        "region_semantics_hash": region_semantics_hash(version=region_version),
        "phase_margin_semantics_version": phase_margin_version,
        "change_scope": "region_classifier_only",
    }


def benchmark_v2_hash(*, region_version: str = V2_SEMANTICS,
                      phase_margin_version: str = PHASE_MARGIN_SEMANTICS) -> str:
    definition = benchmark_v2_definition(region_version=region_version,
                                         phase_margin_version=phase_margin_version)
    return sha256(json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
