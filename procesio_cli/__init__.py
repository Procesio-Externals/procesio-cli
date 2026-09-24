"""PROCESIO CLI + Agent - installed entry points.

The repository is path-based: a tool is a folder under ``tools/`` with its own
``main.py``, and the runner resolves it by path rather than importing it by name
(``google-calendar`` is a folder name, never a module name). So the wheel ships the
whole tree under this package and puts this directory on ``sys.path``, which makes
``import tools`` and ``import registry`` resolve exactly as they do in a clone.

Running from a clone is unchanged and still documented:
``uv sync`` then ``python scripts/run-tool.py <tool> <action>``.
"""
from pathlib import Path

__version__ = "0.1.0"

#: The bundled repository root. In a wheel this directory holds tools/, agents/,
#: scripts/, skills/ and registry.py; in a clone it is the package beside them.
ROOT = Path(__file__).resolve().parent
