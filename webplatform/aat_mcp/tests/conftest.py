import sys
from pathlib import Path

# Make the aat_mcp package modules (bridge, server) importable under pytest's
# importlib mode without turning aat_mcp into an installed package.
_AAT_MCP = Path(__file__).resolve().parents[1]
if str(_AAT_MCP) not in sys.path:
    sys.path.insert(0, str(_AAT_MCP))
