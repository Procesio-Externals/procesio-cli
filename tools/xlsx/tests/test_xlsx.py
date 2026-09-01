"""Tests for the xlsx tool: pure reader + dispatch + manifest sync."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools._lib.manifest import load_tool
from tools.xlsx import main, reader


# --- pure reader ------------------------------------------------------------

def test_list_sheets(sample_xlsx):
    sheets = reader.list_sheets(sample_xlsx)
    titles = [s["title"] for s in sheets]
    assert titles == ["Data", "Empty"]
    data = next(s for s in sheets if s["title"] == "Data")
    assert data["columns"] == 3


def test_read_sheet_skips_empty_and_trims(sample_xlsx):
    out = reader.read_sheet(sample_xlsx, "Data")
    assert out["sheet"] == "Data"
    # Blank middle row dropped: header + 2 data rows.
    assert out["rows"] == [
        ["Item", "Cost", "Notă"],
        ["Hosting", 1200, "lunară"],
        ["Support", 800, "ăîâșț"],
    ]
    assert out["truncated"] is False


def test_read_sheet_default_first(sample_xlsx):
    out = reader.read_sheet(sample_xlsx)
    assert out["sheet"] == "Data"


def test_read_sheet_max_rows(sample_xlsx):
    out = reader.read_sheet(sample_xlsx, "Data", max_rows=1)
    assert len(out["rows"]) == 1
    assert out["truncated"] is True


def test_read_empty_sheet(sample_xlsx):
    out = reader.read_sheet(sample_xlsx, "Empty")
    assert out["rows"] == []


def test_dump_text(sample_xlsx):
    text = reader.dump_text(sample_xlsx)
    assert "SHEET: Data" in text
    assert "Hosting | 1200 | lunară" in text
    assert "ăîâșț" in text


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        reader.list_sheets("nope.xlsx")


def test_wrong_extension(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n")
    with pytest.raises(ValueError):
        reader.list_sheets(str(p))


# --- dispatch ---------------------------------------------------------------

def test_dispatch_list_sheets(sample_xlsx):
    result = main.dispatch("list-sheets", ["--path", sample_xlsx])
    assert [s["title"] for s in result["sheets"]] == ["Data", "Empty"]


def test_dispatch_read_sheet(sample_xlsx):
    result = main.dispatch("read-sheet", ["--path", sample_xlsx, "--sheet", "Data"])
    assert result["rows"][0] == ["Item", "Cost", "Notă"]


def test_dispatch_dump_save(sample_xlsx, tmp_path):
    out = tmp_path / "dump.txt"
    result = main.dispatch("dump", ["--path", sample_xlsx, "--save", str(out)])
    assert out.read_text(encoding="utf-8").count("SHEET:") == 2
    assert result["savedTo"] == str(out.resolve())


def test_dispatch_unknown_action():
    with pytest.raises(main.UsageError):
        main.dispatch("nope", [])


def test_dispatch_missing_required_arg():
    with pytest.raises(main.UsageError):
        main.dispatch("list-sheets", [])


# --- manifest sync ----------------------------------------------------------

def test_manifest_sync():
    tool_root = Path(main.__file__).resolve().parent
    m = load_tool(tool_root / "tool.yaml")
    assert set(m.action_names()) == set(main.ACTIONS)
