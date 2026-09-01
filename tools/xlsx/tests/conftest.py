"""Fixtures for the xlsx tool: sys.path + a generated sample workbook."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# openpyxl is an OPTIONAL dependency (reading .xlsx workbooks), so a plain install does not
# have it. These tests then FAIL, which reads as a broken repository rather
# than as an extra nobody asked for. Skip instead, with the reason visible.
pytest.importorskip('openpyxl', reason="install the extra that provides openpyxl")

FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))


@pytest.fixture
def sample_xlsx(tmp_path):
    """A 2-sheet workbook with a header row, data, a blank row, and diacritics."""
    from openpyxl import Workbook
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Data"
    ws1.append(["Item", "Cost", "Notă"])
    ws1.append(["Hosting", 1200, "lunară"])
    ws1.append([None, None, None])          # blank row -> skipped
    ws1.append(["Support", 800, "ăîâșț"])
    ws2 = wb.create_sheet("Empty")
    p = tmp_path / "sample.xlsx"
    wb.save(str(p))
    return str(p)
