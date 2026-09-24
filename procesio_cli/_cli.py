"""Console-script entry points.

Each one runs the corresponding script from the bundled tree, unchanged. Delegating
with ``runpy`` rather than importing a ``main()`` keeps one code path: the script a
clone runs and the script an installed package runs are the same file, so they cannot
drift apart.
"""
from __future__ import annotations

import runpy
import sys

from . import ROOT


def _run(script: str, *, where: str = "scripts") -> int:
    path = ROOT / where / script
    if not path.is_file():
        print(f"error: {script} is missing from the installed package", file=sys.stderr)
        return 2
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)          # so `import tools` / `import registry` resolve
    sys.argv = [str(path), *sys.argv[1:]]
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:             # the scripts exit through sys.exit
        return int(exc.code or 0)
    return 0


def run_tool() -> int:
    return _run("run-tool.py")


def run_agent() -> int:
    return _run("run-agent.py")


def list_tools() -> int:
    return _run("list-tools.py")


def get_skill() -> int:
    return _run("get-skill.py")


def mcp_server() -> int:
    """The full stdio MCP server, as a command instead of an absolute path.

    Configuring it used to mean writing /abs/path/to/the/clone into every client's
    JSON. Installed, the client names a command and the path problem disappears.

    Six generic tools over the whole registry, so any tool you add shows up without
    integration code. That reach is the point, and it is also why this is not what the
    plugin launches - see mcp_chat_server.
    """
    return _run("server.py", where="webplatform/aat_mcp")


def mcp_chat_server() -> int:
    """The curated stdio MCP server: one named tool per operation.

    What `.mcp.json` launches, and what a general chat client should get. Every tool
    states what it does and none of them forward a caller-supplied action, which is
    what makes the surface reviewable - by a person reading a directory listing, and
    by a model choosing between tools.

    `procesio-mcp` is still there for anyone who wants the whole registry.
    """
    return _run("chat_server.py", where="webplatform/aat_mcp")
