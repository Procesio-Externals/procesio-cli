"""Test setup for the dashboard package.

Puts the repo root on sys.path (so `import dashboard...` / `import registry`
resolve under importlib mode) and forces keyring's Windows backend to skip the
auto-detection that can block in a console-less process.
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("PYTHON_KEYRING_BACKEND",
                      "keyring.backends.Windows.WinVaultKeyring")
