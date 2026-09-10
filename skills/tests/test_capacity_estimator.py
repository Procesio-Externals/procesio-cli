from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills/procesio-platform-advisor/scripts/estimate_capacity.py"


def module():
    spec = importlib.util.spec_from_file_location("capacity_estimator", SCRIPT)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def payload():
    return {"executions": 10000, "available_seconds": 3600,
            "mean_active_compute_seconds": 2, "mean_occupied_seconds": 20,
            "busy_interval_arrival_rate": 5, "safety_factor": 1.25}


def test_documented_example_requires_capacity_source_before_ee_conversion():
    data = payload()
    estimate = module().estimate(data)
    assert estimate["compute_work_seconds"] == 20000
    assert estimate["occupied_slot_seconds"] == 200000
    assert estimate["average_occupied_slots"] == pytest.approx(55.55555556)
    assert estimate["planned_slots"] == 125
    assert estimate["slot_based_ee_lower_bound"] is None
    data.update(verified_slots_per_ee=10, capacity_source="hypothetical example, not a product limit")
    assert module().estimate(data)["slot_based_ee_lower_bound"] == 13


@pytest.mark.parametrize("key,value", [
    ("executions", True), ("executions", 1.5), ("available_seconds", 0),
    ("mean_occupied_seconds", None), ("safety_factor", 0.5),
    ("mean_active_compute_seconds", float("nan")),
    ("busy_interval_arrival_rate", float("inf")), ("executions", -1),
])
def test_invalid_units_and_nonfinite_inputs_fail(key, value):
    data = payload()
    data[key] = value
    with pytest.raises(ValueError):
        module().estimate(data)


def test_unattributed_capacity_and_unknown_fields_fail():
    with pytest.raises(ValueError):
        module().estimate(dict(payload(), verified_slots_per_ee=10))
    with pytest.raises(ValueError):
        module().estimate(dict(payload(), slots_per_ee=10))


def test_zero_workload_and_occupied_wait_are_distinct():
    assert module().estimate(dict(payload(), executions=0, busy_interval_arrival_rate=0))["planned_slots"] == 0
    estimate = module().estimate(dict(payload(), mean_active_compute_seconds=0))
    assert estimate["compute_work_seconds"] == 0
    assert estimate["planned_slots"] == 125


def test_overflow_is_a_validation_error():
    with pytest.raises(ValueError):
        module().estimate(dict(payload(), executions=10 ** 308, mean_occupied_seconds=10 ** 308))


@pytest.mark.parametrize("content,code", [("not json", 1), ("[]", 1), (" " * 65537, 1), (None, 0)])
def test_real_cli_has_one_json_result_and_no_traceback(tmp_path, content, code):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload()) if content is None else content)
    result = subprocess.run([sys.executable, str(SCRIPT), "--input", str(source)],
                            capture_output=True, text=True)
    assert result.returncode == code
    response = json.loads(result.stdout)
    assert ("error" in response) == bool(code)
    assert not result.stderr
