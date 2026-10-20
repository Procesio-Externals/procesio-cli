"""Guards the HTML -> DOCX converter that is pasted into a PROCESIO Node action.

The asset runs inside the platform's Node sandbox (no require of fs/zlib/buffer), so the
end-to-end check runs it in a bare vm context the same way. Skipped when no `node` binary
is on PATH; the placeholder check always runs.
"""
from __future__ import annotations

import base64
import io
import json
import re
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ASSET = Path(__file__).resolve().parents[1] / "assets" / "html2docx" / "html2docx.js"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"

HTML = """<html lang="ro"><head><style>
@media print { @page { size: A4; margin: 1cm } }
html, body { margin: 0 }
.page { padding: 0 0.5cm 0 1.5cm; font-family: Arial, sans-serif; font-size: 10pt; line-height: 1.241 }
.hl { background: #FFFF00 } .c { text-align: center }
table.bd td { border: 1px solid #000; padding: 0 0.1cm }
.salt { page-break-before: always; height: 0 }
</style></head><body><div class="page">
<p class="c"><b>CONTRACT</b> nr. <span class="hl">____</span> &icirc;ncheiat &#537;i semnat</p>
<table class="bd" style="width:100%"><colgroup><col style="width:30%"><col style="width:70%"></colgroup>
<tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>
<div class="salt"></div><ul><li>unu</li><li>doi</li></ul>
</div></body></html>"""


def _convert(tmp_path, html):
    """Run the asset in a bare vm context (the PROCESIO Node sandbox profile) and return
    its result dict. Caller guards with skipif(node missing)."""
    runner = tmp_path / "run.js"
    runner.write_text(
        "const vm=require('vm'),fs=require('fs');"
        "const src=fs.readFileSync(process.argv[2],'utf8');"
        "const ctx=vm.createContext({console,Date,setTimeout,clearTimeout,Promise});"
        "const r=vm.runInContext(src+';H2D.convert('+JSON.stringify(process.argv[3])+',null,true)',ctx);"
        "process.stdout.write(JSON.stringify(r));",
        encoding="utf-8",
    )
    b64 = base64.b64encode(html.encode("utf-8")).decode()
    out = subprocess.run(["node", str(runner), str(ASSET), b64], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_asset_has_no_placeholder_text():
    # The platform substitutes `<%...%>` textually anywhere in a Node body, comments included.
    assert "<%" not in ASSET.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node binary not available")
def test_converts_in_a_bare_sandbox(tmp_path):
    res = _convert(tmp_path, HTML)
    report = res["report"]
    assert report["ok"] and report["tables"] == 1 and report["lists"] == 1
    # padding of the single wrapper is folded into the page margins
    assert report["page"]["marginsCm"]["left"] == pytest.approx(2.5, abs=0.01)
    assert report["page"]["marginsCm"]["right"] == pytest.approx(1.5, abs=0.01)

    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(res["base64"])))
    assert zf.testzip() is None
    for name in zf.namelist():
        if name.endswith((".xml", ".rels")):
            ET.fromstring(zf.read(name))
    doc = zf.read("word/document.xml").decode("utf-8")
    assert "încheiat și semnat" in doc                       # entities decoded, UTF-8 kept
    assert '<w:highlight w:val="yellow"/>' in doc             # background #FFFF00 -> highlight
    assert '<w:vMerge w:val="restart"/>' in doc               # rowspan
    assert "<w:pageBreakBefore/>" in doc                      # page-break-before on an empty div
    assert re.search(r'w:line="259" w:lineRule="auto"', doc)  # CSS 1.241 on Arial == Word 1.08
    assert "word/numbering.xml" in zf.namelist()


@pytest.mark.skipif(shutil.which("node") is None, reason="node binary not available")
def test_package_integrity_is_what_word_checks(tmp_path):
    """A zip/XML-valid .docx can still be one Word repairs. The triggers Word actually
    rejects on are machine-checkable: dangling relationship ids, parts missing from
    [Content_Types].xml, and list refs with no numbering part. Assert none of them."""
    res = _convert(tmp_path, HTML)
    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(res["base64"])))
    doc = ET.fromstring(zf.read("word/document.xml"))

    # 1. every r:id / r:embed in document.xml resolves to a declared relationship
    refs = set()
    for el in doc.iter():
        for attr, val in el.attrib.items():
            if attr in (R + "id", R + "embed"):
                refs.add(val)
    rels = {r.get("Id") for r in ET.fromstring(zf.read("word/_rels/document.xml.rels"))}
    assert refs <= rels, f"dangling relationship ids (Word would repair): {refs - rels}"

    # 2. every part is covered by [Content_Types].xml (default extension or explicit override)
    ct = ET.fromstring(zf.read("[Content_Types].xml"))
    defaults = {d.get("Extension", "").lower() for d in ct.findall(CT + "Default")}
    overrides = {o.get("PartName") for o in ct.findall(CT + "Override")}
    for name in zf.namelist():
        if name.endswith("/") or name == "[Content_Types].xml":
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        assert ext in defaults or ("/" + name) in overrides, f"part not in [Content_Types].xml: {name}"

    # 3. a list reference implies the numbering part exists
    if any(True for _ in doc.iter(W + "numPr")):
        assert "word/numbering.xml" in zf.namelist()


@pytest.mark.skipif(shutil.which("node") is None, reason="node binary not available")
def test_unsupported_css_is_reported_not_silent(tmp_path):
    """Layout the converter cannot do (flex/grid/float) must surface as a warning in the
    report, so an author learns why side-by-side boxes stacked instead of guessing."""
    html = ('<html><body>'
            '<div style="display:flex"><div>a</div><div>b</div></div>'
            '<div style="display:grid"><div>c</div></div>'
            '<div style="float:left">d</div>'
            '</body></html>')
    res = _convert(tmp_path, html)
    warns = " ".join(res["report"]["warnings"]).lower()
    assert "flex" in warns and "grid" in warns and "float" in warns, res["report"]["warnings"]
