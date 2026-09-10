#!/usr/bin/env python3
"""Calculate single-class demand from explicit measurements; never call PROCESIO.

Python 3.11+, standard library only. Reads <=64 KiB JSON via --input; writes one
JSON result to stdout, no files. EE conversion requires caller-supplied capacity
and source; this records an assumption, not independent product verification.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

REQUIRED = {"executions", "available_seconds", "mean_active_compute_seconds",
            "mean_occupied_seconds", "busy_interval_arrival_rate", "safety_factor"}
OPTIONAL = {"verified_slots_per_ee", "capacity_source"}


def _number(data: dict, name: str, minimum: float = 0, *, positive: bool = False) -> float:
    value = data[name]
    if type(value) not in (int, float):
        raise ValueError("numeric fields must be finite numbers, not Boolean or null")
    try:
        valid = math.isfinite(value) and value >= minimum and (not positive or value > 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("numeric field outside its finite permitted range")
    return value


def estimate(data: dict) -> dict:
    if not isinstance(data, dict) or not REQUIRED <= data.keys() or data.keys() - REQUIRED - OPTIONAL:
        raise ValueError("unknown or missing input fields")
    count = _number(data, "executions")
    if type(count) is not int:
        raise ValueError("executions must be a nonnegative integer")
    available = _number(data, "available_seconds", positive=True)
    compute = _number(data, "mean_active_compute_seconds")
    occupied = _number(data, "mean_occupied_seconds")
    rate = _number(data, "busy_interval_arrival_rate")
    factor = _number(data, "safety_factor", minimum=1)
    capacity = data.get("verified_slots_per_ee")
    if capacity is not None:
        capacity = _number(data, "verified_slots_per_ee", positive=True)
        if type(capacity) is not int or not isinstance(data.get("capacity_source"), str) or not data["capacity_source"].strip():
            raise ValueError("EE conversion needs integer slots and an explicit capacity source")
    elif "capacity_source" in data:
        raise ValueError("a capacity source without capacity is ambiguous")
    try:
        compute_work = count * compute
        slot_work = count * occupied
        average_slots = slot_work / available
        busy_slots = rate * occupied
        demand = max(average_slots, busy_slots) * factor
        finite = all(math.isfinite(value) for value in (compute_work, slot_work, average_slots, busy_slots, demand))
    except OverflowError as exc:
        raise ValueError("calculation overflow") from exc
    if not finite:
        raise ValueError("calculation overflow")
    slots = math.ceil(demand)
    return {
        "schema_version": 1,
        "method": "single_class_steady_state_estimate",
        "compute_work_seconds": compute_work,
        "occupied_slot_seconds": slot_work,
        "average_occupied_slots": average_slots,
        "busy_interval_slots_estimate": busy_slots,
        "planned_slots": slots,
        "slot_based_ee_lower_bound": (slots + capacity - 1) // capacity if capacity else None,
        "capacity_basis": "caller_supplied" if capacity else "not_supplied",
        "limitations": ["Not a peak, latency, SLA or price guarantee.",
                        "Verify occupancy, compute throughput, memory, quotas and availability separately.",
                        "For overlapping workload classes, model joint demand before sizing shared capacity."],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as handle:
            content = handle.read(65537)
        if len(content) > 65536:
            raise ValueError("input exceeds 64 KiB")
        result = estimate(json.loads(content))
    except (OSError, ValueError, OverflowError):
        print(json.dumps({"error": {"code": "invalid_capacity_input",
                                   "message": "Provide a readable, bounded JSON object with valid measured units.",
                                   "details": {}}}))
        return 1
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
