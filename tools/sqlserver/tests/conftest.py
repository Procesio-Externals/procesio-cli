"""Put the framework root on sys.path so `from tools...` imports work."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

# pyodbc is an OPTIONAL dependency (the SQL Server driver), so a plain install does not
# have it. These tests then FAIL, which reads as a broken repository rather
# than as an extra nobody asked for. Skip instead, with the reason visible.
pytest.importorskip('pyodbc', reason="install the extra that provides pyodbc")

FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))
