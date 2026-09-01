"""framework-map tool entrypoint - action dispatch.

Regenerates the interactive bilingual (EN default / RO) framework map HTML from
the live registry. JSON in / JSON out. No secrets, no user data - the generated
file is a build artifact (it does reflect current credential presence via the
readiness dots, nothing more).
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent
FRAMEWORK_ROOT = TOOL_ROOT.parents[1]
_VENV_PY = FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

import argparse  # noqa: E402

for _p in (str(FRAMEWORK_ROOT), str(TOOL_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools._lib.io import emit, fail, log  # noqa: E402
import fm_builder  # noqa: E402


class ActionDef:
    def __init__(self, add_args, run, description=""):
        self._add_args = add_args
        self.run = run
        self.description = description

    def add_args(self, parser):
        self._add_args(parser)


def _add_build_args(p):
    p.add_argument("--out", default="framework-map.html",
                   help="Output path for the HTML (relative paths resolve from the repo root).")


def _run_build(args):
    log("extracting registry + assembling map ...")
    html, stats = fm_builder.build_html(FRAMEWORK_ROOT)
    if not html.rstrip().endswith("</html>"):
        fail("assembly_error", "generated HTML is truncated (missing </html>)")
    out = Path(args.out)
    if not out.is_absolute():
        out = FRAMEWORK_ROOT / out
    data = html.encode("utf-8")
    out.write_bytes(data)  # bytes, not write_text: avoid Windows CRLF translation
    size = out.stat().st_size
    if size != len(data):
        fail("write_mismatch", "written byte count does not match generated HTML",
             {"written": size, "expected": len(data)})
    log(f"wrote {out} ({size} bytes)")
    emit({"path": str(out), "bytes": size, **stats})


def _add_check_args(p):
    return None


def _run_check(args):
    emit(fm_builder.stats_only(FRAMEWORK_ROOT))


ACTIONS = {
    "build": ActionDef(_add_build_args, _run_build,
                       "Extract the live registry, translate the catalog to RO, write the single-file HTML map."),
    "check": ActionDef(_add_check_args, _run_check,
                       "Report counts, categories, and catalog strings still missing an RO translation. Writes nothing."),
}


def main():
    parser = argparse.ArgumentParser(prog="framework-map", description="Regenerate the framework map.")
    sub = parser.add_subparsers(dest="action", required=True)
    for name, defn in ACTIONS.items():
        sp = sub.add_parser(name, help=defn.description)
        defn.add_args(sp)
    args = parser.parse_args()
    try:
        ACTIONS[args.action].run(args)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        fail("build_error", str(e), {"action": args.action})


if __name__ == "__main__":
    main()
