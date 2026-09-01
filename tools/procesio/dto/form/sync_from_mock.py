"""Generate canonical form-control goldens from FormBuilder mock.ts (SOURCE OF TRUTH).

The PROCESIO FormBuilder defines every control + its property list in
`docs_info/FormBuilder mock.ts`. The runtime/builder clones one golden per control
from `elements/<type>.json`. This script PARSES the mock and regenerates those
goldens so they are exact, complete, uniformly ordered, and deterministic --
replacing harvest-from-exports (capture_goldens.py), which was limited to controls
that happened to appear in a saved form.

Why parse the mock instead of harvesting:
  * complete   -- every control the FormBuilder ships (incl. ones never harvested)
  * exact      -- keys, render-order, type/category/subCategory/exposed/events all
                  come straight from the source; zero drift by construction
  * repeatable -- same mock in -> identical files out (deterministic ids)

Enum resolution: the mock references ElementConfigType/Category/SubCategory/Event by
member name (imported from '../config', not shipped). Values come from `enum_map.json`
(authoritative). A member missing there is resolved by the fallback rule
(MEMBER -> lower, '_'->'-') and reported as UNVERIFIED -- confirm with the frontend
(UNVERIFIED-ENUMS-QUESTION.md) and paste into enum_map.json. ElementType and
ElementCategory ARE defined in the mock, so they are parsed from it directly.

TEMPLATE_ONLY configs are palette-only (not present in instantiated/saved controls),
so they are intentionally EXCLUDED -- the golden mirrors what the toolbar produces.

Usage:
  python sync_from_mock.py             # dry-run: report changes + unverified enums
  python sync_from_mock.py --write     # (re)write elements/*.json
  python sync_from_mock.py --check     # exit 1 if on-disk goldens != mock (CI guard)
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

DIR = Path(__file__).resolve().parent
MOCK = DIR.parent.parent / "docs_info" / "FormBuilder mock.ts"
ENUMS_TS = DIR.parent.parent / "docs_info" / "form-config-enums.ts"
ELEMENTS = DIR / "elements"
ENUM_MAP = DIR / "enum_map.json"
_CONFIG_ENUMS = ("ElementConfigCategory", "ElementConfigSubCategory",
                 "ElementConfigType", "ElementConfigEvent")

# stable namespace so re-runs produce identical ids (the builder reassigns ids at
# build time anyway; deterministic ids here only keep git diffs clean).
_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "procesio.form.goldens")

# canonical field order within a config object (cosmetic; render order is the
# ORDER OF CONFIGS, preserved from the mock -- not the field order inside one).
_CFG_ORDER = ["id", "key", "label", "placeholder", "tooltip", "category",
              "subCategory", "type", "value", "hasTopDivider", "exposed", "events"]
_TOP_ORDER = ["id", "category", "type", "configs", "parentId", "section"]
_HEADER = {"heading"}
_FOOTER = {"button"}


# --------------------------------------------------------------------------- JS literal parser
class _P:
    """Minimal recursive-descent parser for the JS object/array literals used in the
    mock. Returns plain Python; bare identifiers (ElementConfigType.X, guid()) become
    ('@bare', text) markers so the caller can resolve/strip them."""

    def __init__(self, s, i=0):
        self.s, self.i = s, i

    def ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n,":
                self.i += 1
            elif s[self.i:self.i + 2] == "//":
                while self.i < len(s) and s[self.i] != "\n":
                    self.i += 1
            else:
                break

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c in "\"'`":
            return self.str()
        if c == "-" or c.isdigit():
            return self.num()
        # keyword or bareword
        m = re.match(r"[A-Za-z_$][\w$.]*", self.s[self.i:])
        word = m.group(0)
        self.i += len(word)
        if word == "true":
            return True
        if word == "false":
            return False
        if word in ("null", "undefined"):
            return None
        if self.s[self.i:self.i + 1] == "(":  # function call e.g. guid()
            depth = 0
            while self.i < len(self.s):
                if self.s[self.i] == "(":
                    depth += 1
                elif self.s[self.i] == ")":
                    depth -= 1
                    if depth == 0:
                        self.i += 1
                        break
                self.i += 1
            return ("@bare", word + "()")
        return ("@bare", word)

    def obj(self):
        self.i += 1  # {
        out = {}
        while True:
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
                return out
            # key
            if self.s[self.i] in "\"'`":
                key = self.str()
            else:
                m = re.match(r"[A-Za-z_$][\w$]*", self.s[self.i:])
                key = m.group(0)
                self.i += len(key)
            self.ws()
            assert self.s[self.i] == ":", f"expected ':' at {self.i}"
            self.i += 1
            out[key] = self.value()

    def arr(self):
        self.i += 1  # [
        out = []
        while True:
            self.ws()
            if self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.value())

    def str(self):
        q = self.s[self.i]
        self.i += 1
        buf = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                buf.append(self.s[self.i + 1])
                self.i += 2
                continue
            if c == q:
                self.i += 1
                return "".join(buf)
            buf.append(c)
            self.i += 1
        raise ValueError("unterminated string")

    def num(self):
        m = re.match(r"-?\d+(\.\d+)?([eE][+-]?\d+)?", self.s[self.i:])
        t = m.group(0)
        self.i += len(t)
        return float(t) if ("." in t or "e" in t or "E" in t) else int(t)


def _strip_line_comments(t):
    return "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("//"))


def _parse_enum_block(text, name):
    """Parse `enum <name> { A = "a", ... }` defined inside the mock."""
    m = re.search(r"enum\s+" + name + r"\s*\{(.*?)\}", text, re.S)
    out = {}
    for mm in re.finditer(r"(\w+)\s*=\s*\"([^\"]*)\"", m.group(1)):
        out[mm.group(1)] = mm.group(2)
    return out


# --------------------------------------------------------------------------- generation
class Resolver:
    """Resolves ElementConfig* enum members to their string values. Precedence:
       1. form-config-enums.ts  (authoritative, from the frontend) -- if present
       2. enum_map.json         (committed fallback / manual override)
       3. rule MEMBER->lower,'_'->'-'  (last resort; flagged UNVERIFIED)
    With the enums file present, every member resolves authoritatively (no guessing)."""

    def __init__(self):
        self.maps = {}
        if ENUM_MAP.exists():
            m = json.loads(ENUM_MAP.read_text(encoding="utf-8"))
            self.maps = {k: dict(v) for k, v in m.items()
                         if not k.startswith("_") and isinstance(v, dict)}
        self.from_ts = False
        if ENUMS_TS.exists():
            txt = ENUMS_TS.read_text(encoding="utf-8")
            for name in _CONFIG_ENUMS:
                block = _parse_enum_block(txt, name)
                if block:
                    self.maps.setdefault(name, {}).update(block)  # the TS file wins
                    self.from_ts = True
        self.unverified = {}  # "Enum.MEMBER" -> derived value

    def _rule(self, member):
        return member.lower().replace("_", "-")

    def resolve(self, enum_name, member):
        table = self.maps.get(enum_name, {})
        if member in table:
            return table[member]
        val = self._rule(member)
        self.unverified.setdefault(f"{enum_name}.{member}", val)
        return val


def _bare_member(v):
    """('@bare','ElementConfigType.INPUT') -> ('ElementConfigType','INPUT')."""
    if isinstance(v, tuple) and v and v[0] == "@bare" and "." in v[1]:
        head, _, mem = v[1].partition(".")
        return head, mem
    return None


def _det_id(*parts):
    return str(uuid.uuid5(_NS, "/".join(parts)))


def build_goldens():
    raw = MOCK.read_text(encoding="utf-8")
    text = _strip_line_comments(raw)
    el_types = _parse_enum_block(text, "ElementType")
    el_cats = _parse_enum_block(text, "ElementCategory")
    res = Resolver()

    # locate the elementTemplates array and parse it as one big JS array. Anchor on
    # the assignment '=' so we skip the `ElementTemplate[]` type-annotation brackets.
    eq = text.index("=", text.index("elementTemplates"))
    start = text.index("[", eq)
    arr = _P(text, start).value()  # list of template dicts

    goldens = {}
    stats = {}
    for tpl in arr:
        # top-level type: ElementType.X  ->  string
        bt = _bare_member(tpl["type"])
        etype = el_types[bt[1]] if bt else tpl["type"]
        # top-level category: string literal OR ElementCategory.X
        cat_raw = tpl["category"]
        bc = _bare_member(cat_raw)
        category = el_cats[bc[1]] if bc else cat_raw

        configs_out = []
        skipped_template_only = 0
        unverified_here = 0
        idx = {}
        for c in tpl["configs"]:
            tmem = _bare_member(c["type"])
            type_member = tmem[1] if tmem else None
            if type_member == "TEMPLATE_ONLY":
                skipped_template_only += 1
                continue
            key = c["key"]
            n = idx.get(key, 0)
            idx[key] = n + 1
            o = {"id": _det_id(etype, key, str(n)), "key": key}
            for f in ("label", "placeholder", "tooltip"):
                if f in c:
                    o[f] = c[f]
            o["category"] = res.resolve("ElementConfigCategory", _bare_member(c["category"])[1])
            o["subCategory"] = res.resolve("ElementConfigSubCategory", _bare_member(c["subCategory"])[1])
            before = len(res.unverified)
            o["type"] = res.resolve("ElementConfigType", type_member)
            o["value"] = c.get("value")
            if "hasTopDivider" in c:
                o["hasTopDivider"] = c["hasTopDivider"]
            if "exposed" in c:
                o["exposed"] = c["exposed"]
            if "events" in c and c["events"] is not None:
                evs = c["events"]
                if isinstance(evs, list):
                    o["events"] = [res.resolve("ElementConfigEvent", _bare_member(e)[1]) for e in evs]
            if len(res.unverified) > before:
                unverified_here += 1
            configs_out.append({k: o[k] for k in _CFG_ORDER if k in o})

        section = "header" if etype in _HEADER else "footer" if etype in _FOOTER else "body"
        gold = {"id": _det_id(etype), "category": category, "type": etype,
                "configs": configs_out, "parentId": None, "section": section}
        goldens[etype] = {k: gold[k] for k in _TOP_ORDER}
        stats[etype] = (len(configs_out), skipped_template_only, unverified_here)
    return goldens, stats, res


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


def main(argv):
    write = "--write" in argv
    check = "--check" in argv
    goldens, stats, res = build_goldens()

    on_disk = {p.stem for p in ELEMENTS.glob("*.json")}
    gen = set(goldens)
    changed, created, identical = [], [], []
    for t in sorted(goldens):
        new_txt = _dump(goldens[t])
        path = ELEMENTS / f"{t}.json"
        if not path.exists():
            created.append(t)
        elif path.read_text(encoding="utf-8").strip() != new_txt.strip():
            changed.append(t)
        else:
            identical.append(t)

    # ---- soundness gate: never change a value that an existing golden already had
    # right (shared key+occurrence among non-template-only configs).
    failures = []
    for t in sorted(gen & on_disk):
        old = json.loads((ELEMENTS / f"{t}.json").read_text(encoding="utf-8"))
        oldby, occ = {}, {}
        for c in old.get("configs", []):
            k = c.get("key"); n = occ.get(k, 0); occ[k] = n + 1
            oldby[(k, n)] = c
        nocc = {}
        for c in goldens[t]["configs"]:
            k = c["key"]; n = nocc.get(k, 0); nocc[k] = n + 1
            oc = oldby.get((k, n))
            if not oc:
                continue
            # type/category/subCategory/exposed are deterministic from enums and
            # present in both -> any diff means the enum map is wrong (hard fail).
            for attr in ("type", "category", "subCategory", "exposed"):
                if attr in oc and oc.get(attr) != c.get(attr):
                    failures.append(f"{t}.{k}#{n}: {attr} disk={oc.get(attr)!r} new={c.get(attr)!r}")
            # events: a stale golden may simply LACK events the mock defines -> adding
            # them is a correction, not a failure. Only a genuine CONTRADICTION (old had
            # a non-empty list that the mock disagrees with) is a soundness problem.
            oe, ne = oc.get("events") or [], c.get("events") or []
            if oe and oe != ne:
                failures.append(f"{t}.{k}#{n}: events disk={oc.get('events')} new={c.get('events')} (CONTRADICTION)")

    print("# SYNC: FormBuilder mock.ts -> form-control goldens\n")
    print(f"templates parsed : {len(goldens)}")
    print(f"on disk          : {len(on_disk)}")
    print(f"to CREATE ({len(created)}): {created}")
    print(f"to CHANGE ({len(changed)}): {changed}")
    print(f"identical ({len(identical)})")
    print(f"\nper-element (configs / template-only-skipped / unverified-typed-configs):")
    for t in sorted(stats):
        a, b, c = stats[t]
        mark = "  <-- has UNVERIFIED enum value(s)" if c else ""
        print(f"  {t:20s} {a:2d} / {b} / {c}{mark}")

    print(f"\n## soundness check (must be empty): {len(failures)} mismatch(es) vs existing goldens")
    for f in failures:
        print(f"  !! {f}")

    print(f"\n## UNVERIFIED enum members ({len(res.unverified)}) -- value derived by rule, confirm w/ frontend:")
    for k in sorted(res.unverified):
        print(f"  {k:55s} -> {res.unverified[k]!r}")

    if failures:
        print("\nABORT: soundness check failed -- fix enum_map.json before writing.")
        return 2
    if check:
        drift = created + changed
        if drift:
            print(f"\n--check: {len(drift)} golden(s) differ from mock: {drift}")
            return 1
        print("\n--check: all goldens match the mock.")
        return 0
    if write:
        for t, g in goldens.items():
            (ELEMENTS / f"{t}.json").write_text(_dump(g), encoding="utf-8")
        print(f"\nWROTE {len(goldens)} goldens to {ELEMENTS}")
    else:
        print("\nDRY-RUN (no files written). Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
