# -*- coding: utf-8 -*-
"""framework-map builder: extract the live registry, compress it, apply RO
translations, and assemble the single-file bilingual HTML map.

Pure framework logic - reads only the registry (manifests) and the sibling
asset files (fm_strings, fm_ro_catalog, styles.css, app.js). No user data.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from string import Template

import yaml

import fm_strings
import fm_ro_catalog

TOOL_ROOT = Path(__file__).resolve().parent

# ---- category map: which explorer group each tool belongs to ----------------
from fm_catalog import CAT, FALLBACK_CAT  # noqa: E402  (the census, per install)


# ---- 1. extract: read the live registry -------------------------------------
def extract(framework_root: Path) -> dict:
    if str(framework_root) not in sys.path:
        sys.path.insert(0, str(framework_root))
    import importlib
    import registry
    importlib.reload(registry)  # pick up freshly added tools within one process
    return {
        "tools": registry.list_tools(),
        "agents": registry.list_agents(),
        "skills": registry.list_skills(),
    }


# ---- 2. compress: full registry -> lean, embeddable EN data ------------------
def _short_secret(s):
    desc = (s.get("description") or "").split(".")[0].strip()
    return {"name": s["name"], "desc": desc[:90]}


def _compact_action(a):
    args = [{"n": g["name"], "r": bool(g.get("required")), "d": (g.get("description") or "")[:70]}
            for g in a.get("args", [])]
    return {"n": a["name"], "d": (a.get("description") or "")[:220], "a": args}


def compress(dump: dict) -> dict:
    tools = []
    for t in dump["tools"]:
        r = t.get("routing") or {}
        tools.append({
            "name": t["name"], "cat": CAT.get(t["name"], FALLBACK_CAT), "desc": t.get("description", ""),
            "triggers": r.get("triggers"), "primary": r.get("primary_action"), "example": r.get("example"),
            "secrets": [_short_secret(s) for s in t.get("secrets", [])], "ready": t.get("ready"),
            "actions": [_compact_action(a) for a in t.get("actions", [])],
        })
    agents = []
    for a in dump["agents"]:
        r = a.get("routing") or {}
        agents.append({
            "name": a["name"], "desc": a.get("description", ""), "tools": a.get("tools", []),
            "triggers": r.get("triggers"), "primary": r.get("primary_action"), "example": r.get("example"),
            "actions": [_compact_action(ac) for ac in a.get("actions", [])],
        })
    skills = [{"name": s["name"], "desc": s.get("description", "")} for s in dump["skills"]]
    return {"tools": tools, "agents": agents, "skills": skills}


def categories(data: dict) -> dict:
    out = {}
    for t in data["tools"]:
        out[t["cat"]] = out.get(t["cat"], 0) + 1
    return out


def uncategorized(data: dict) -> list:
    return sorted(t["name"] for t in data["tools"] if t["cat"] == FALLBACK_CAT)


# ---- 3. translate: EN data -> RO data (catalog layer), with fallback ---------
def translate_ro(data_en: dict):
    ro = copy.deepcopy(data_en)
    miss = {"tool_desc": [], "triggers": [], "agent_desc": [], "skill_desc": [], "category": []}
    seen_cat_miss = set()
    for t in ro["tools"]:
        if t["cat"] in fm_ro_catalog.CATS:
            t["cat"] = fm_ro_catalog.CATS[t["cat"]]
        elif t["cat"] not in seen_cat_miss:
            seen_cat_miss.add(t["cat"]); miss["category"].append(t["cat"])
        if t["name"] in fm_ro_catalog.TOOL_DESC:
            t["desc"] = fm_ro_catalog.TOOL_DESC[t["name"]]
        else:
            miss["tool_desc"].append(t["name"])
        if t.get("triggers"):
            nt = []
            for x in t["triggers"]:
                if x in fm_ro_catalog.TRIG:
                    nt.append(fm_ro_catalog.TRIG[x])
                else:
                    miss["triggers"].append(x); nt.append(x)
            t["triggers"] = nt
    for a in ro["agents"]:
        if a["name"] in fm_ro_catalog.AGENT_DESC:
            a["desc"] = fm_ro_catalog.AGENT_DESC[a["name"]]
        else:
            miss["agent_desc"].append(a["name"])
        if a.get("triggers"):  # agent triggers were previously left untranslated
            nt = []
            for x in a["triggers"]:
                if x in fm_ro_catalog.TRIG:
                    nt.append(fm_ro_catalog.TRIG[x])
                else:
                    miss["triggers"].append(x); nt.append(x)
            a["triggers"] = nt
    for s in ro["skills"]:
        if s["name"] in fm_ro_catalog.SKILL_DESC:
            s["desc"] = fm_ro_catalog.SKILL_DESC[s["name"]]
        else:
            miss["skill_desc"].append(s["name"])
    miss = {k: v for k, v in miss.items() if v}
    return ro, miss


# ---- 4. assemble: data + templates + assets -> single HTML -------------------
SVG = r"""<svg viewBox="0 0 920 500" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" role="img" aria-label="architecture diagram">
  <defs>
    <marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8a93a3"/></marker>
    <marker id="ahg" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#047857"/></marker>
    <marker id="ahs" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#b45309"/></marker>
  </defs>
  <rect x="40" y="18" width="210" height="48" rx="10" fill="#eef4ff" stroke="#2563eb"/>
  <text x="145" y="40" text-anchor="middle" font-size="14" font-weight="700" fill="#1d3a8a">$svg_you</text>
  <text x="145" y="56" text-anchor="middle" font-size="10.5" fill="#4b6bb5">$svg_you2</text>
  <rect x="355" y="18" width="210" height="48" rx="10" fill="#fff8ec" stroke="#f3ddb0"/>
  <text x="460" y="40" text-anchor="middle" font-size="14" font-weight="700" fill="#b45309">$svg_skill</text>
  <text x="460" y="56" text-anchor="middle" font-size="10.5" fill="#b07a2a">$svg_skill2</text>
  <rect x="670" y="18" width="210" height="48" rx="10" fill="#fef2f2" stroke="#f6cccc"/>
  <text x="775" y="40" text-anchor="middle" font-size="14" font-weight="700" fill="#b91c1c">$svg_timer</text>
  <text x="775" y="56" text-anchor="middle" font-size="10.5" fill="#c2554e">$svg_timer2</text>
  <rect x="315" y="116" width="290" height="58" rx="13" fill="#eef2ff" stroke="#4338ca" stroke-width="1.4"/>
  <text x="460" y="140" text-anchor="middle" font-size="15.5" font-weight="700" fill="#3730a3">$svg_orch</text>
  <text x="460" y="159" text-anchor="middle" font-size="10.5" fill="#5b53c4">$svg_orch2</text>
  <rect x="688" y="120" width="192" height="50" rx="11" fill="#eef2ff" stroke="#4338ca"/>
  <text x="784" y="141" text-anchor="middle" font-size="13.5" font-weight="700" fill="#3730a3">$svg_sched</text>
  <text x="784" y="158" text-anchor="middle" font-size="10" fill="#5b53c4">$svg_sched2</text>
  <rect x="250" y="230" width="196" height="56" rx="13" fill="#f5f3ff" stroke="#d6ccf7" stroke-width="1.4"/>
  <text x="348" y="254" text-anchor="middle" font-size="15" font-weight="700" fill="#6d28d9">$svg_agents</text>
  <text x="348" y="272" text-anchor="middle" font-size="10.5" fill="#8257d6">$svg_agents2</text>
  <rect x="486" y="230" width="230" height="56" rx="13" fill="#ecfeff" stroke="#a5e8ef" stroke-width="1.4"/>
  <text x="601" y="254" text-anchor="middle" font-size="15" font-weight="700" fill="#0e7490">$svg_tools</text>
  <text x="601" y="272" text-anchor="middle" font-size="10.5" fill="#2a8ba3">$svg_tools2</text>
  <rect x="756" y="230" width="124" height="56" rx="11" fill="#fff8ec" stroke="#f3ddb0"/>
  <text x="818" y="252" text-anchor="middle" font-size="12" font-weight="700" fill="#92600a">$svg_cred1</text>
  <text x="818" y="268" text-anchor="middle" font-size="12" font-weight="700" fill="#92600a">$svg_cred2</text>
  <rect x="300" y="330" width="416" height="46" rx="10" fill="#f7f9fc" stroke="#e5e8ef"/>
  <text x="508" y="351" text-anchor="middle" font-size="12" font-weight="600" fill="#45506a">$svg_ext</text>
  <text x="508" y="367" text-anchor="middle" font-size="10.5" fill="#6c7690">$svg_ext2</text>
  <rect x="40" y="416" width="840" height="58" rx="13" fill="#ecfdf5" stroke="#b3e6ce" stroke-width="1.4"/>
  <text x="460" y="440" text-anchor="middle" font-size="14.5" font-weight="700" fill="#047857">$svg_store</text>
  <text x="460" y="459" text-anchor="middle" font-size="10.5" fill="#3f9e7c">$svg_store2</text>
  <line x1="145" y1="66" x2="360" y2="114" stroke="#8a93a3" stroke-width="1.5" marker-end="url(#ah)"/>
  <line x1="460" y1="66" x2="460" y2="112" stroke="#b45309" stroke-width="1.4" stroke-dasharray="4 4" marker-end="url(#ahs)"/>
  <text x="470" y="94" font-size="10" fill="#b07a2a">$svg_l_know</text>
  <line x1="775" y1="66" x2="784" y2="116" stroke="#8a93a3" stroke-width="1.5" marker-end="url(#ah)"/>
  <line x1="688" y1="150" x2="609" y2="148" stroke="#8a93a3" stroke-width="1.5" marker-end="url(#ah)"/>
  <line x1="418" y1="174" x2="360" y2="226" stroke="#8a93a3" stroke-width="1.5" marker-end="url(#ah)"/>
  <line x1="512" y1="174" x2="580" y2="226" stroke="#8a93a3" stroke-width="1.5" marker-end="url(#ah)"/>
  <text x="392" y="208" font-size="9.5" fill="#8a93a3">$svg_l_routes</text>
  <line x1="446" y1="258" x2="482" y2="258" stroke="#6d28d9" stroke-width="1.6" marker-end="url(#ah)"/>
  <text x="447" y="250" font-size="9.5" fill="#6d28d9">$svg_l_drives</text>
  <line x1="756" y1="258" x2="720" y2="258" stroke="#b45309" stroke-width="1.4" stroke-dasharray="4 4" marker-end="url(#ahs)"/>
  <text x="700" y="222" font-size="9.5" fill="#b07a2a" text-anchor="middle">$svg_l_secrets</text>
  <line x1="595" y1="286" x2="545" y2="326" stroke="#8a93a3" stroke-width="1.5" marker-end="url(#ah)"/>
  <line x1="270" y1="286" x2="270" y2="416" stroke="#047857" stroke-width="1.3" stroke-dasharray="5 4" marker-start="url(#ahg)" marker-end="url(#ahg)"/>
  <line x1="650" y1="376" x2="650" y2="416" stroke="#047857" stroke-width="1.3" stroke-dasharray="5 4" marker-start="url(#ahg)" marker-end="url(#ahg)"/>
  <line x1="150" y1="416" x2="150" y2="150" stroke="#047857" stroke-width="1.3" stroke-dasharray="5 4" marker-start="url(#ahg)" marker-end="url(#ahg)"/>
  <text x="278" y="308" font-size="9.5" fill="#047857">$svg_l_rw</text>
</svg>"""

# Stands in for PART_A wherever the architecture narrative is not shipped. Uses the
# same live counters, so it is never out of date with what the registry found.
GENERIC_HERO = """<section class="hero">
  <h1>$hero_h</h1>
  <p class="lead">$hero_p</p>
  <div class="stats">
    <div class="stat"><b>$NTOOLS</b><span>$w_tools</span></div>
    <div class="stat"><b>$NAGENTS</b><span>$w_agents</span></div>
    <div class="stat"><b>$NSKILLS</b><span>$w_skills</span></div>
    <div class="stat"><b>$NACTIONS</b><span>$w_actions</span></div>
  </div>
</section>"""

PART_A = globals().get("PART_A", GENERIC_HERO)

PART_B = globals().get("PART_B", "")

HEADER = """<header class="top"><div class="top-in">
  <div class="brand"><span class="dot"></span>Agents &amp; Tools</div>
  <nav class="nav">
    <a href="#explore" data-t="nav_explore">Explore</a>
  </nav>
  <div class="langtoggle" role="group" aria-label="Language">
    <button data-lang="en" class="on">EN</button>
    <button data-lang="ro">RO</button>
  </div>
</div></header>"""

EXPLORE = """<section class="band" id="explore">
  <div class="kicker" data-t="exp_kicker">Every capability, drillable</div>
  <h2 data-t="exp_h2">Explore everything</h2>
  <p class="intro" data-t="exp_intro">The full registry, straight from the manifests.</p>
  <div class="exp-bar exp-tools">
    <input id="search" type="search" placeholder="Search..." autocomplete="off">
    <div class="tabs">
      <button data-tab="tools" data-t="tab_tools" class="on">Tools</button>
      <button data-tab="agents" data-t="tab_agents">Agents</button>
      <button data-tab="skills" data-t="tab_skills">Skills</button>
    </div>
    <button class="btn" id="expand-all" data-t="ctl_expand">Expand all</button>
    <button class="btn" id="collapse-all" data-t="ctl_collapse">Collapse all</button>
    <span class="expcount" id="expcount"></span>
  </div>
  <div id="emptymsg" class="empty" style="display:none" data-t="empty">Nothing matches that search.</div>
  <div id="tools-view"></div>
  <div id="agents-view" style="display:none"></div>
  <div id="skills-view" style="display:none"></div>
</section>"""


_SCHED_FALLBACK = {
    "en": '<b>Live today:</b> no scheduled jobs yet. Add entries to schedule.yaml '
          'and the hourly tick runs whatever is due.',
    "ro": '<b>Activ azi:</b> niciun job programat încă. Adaugă intrări în '
          'schedule.yaml şi tick-ul orar rulează ce e scadent.',
}
_CANON_FOLDERS = ["config", "state", "prompts", "sessions", "exports", "schedule"]
_FOLDER_EXTRA = {
    "en": {"state": "machine-owned runtime state, per component",
           "prompts": "your personal prompt copies (base stays in git)",
           "exports": "human-readable dumps of the store"},
    "ro": {"state": "stare runtime deţinută de maşină, per componentă",
           "prompts": "copiile tale personale de prompt (baza rămâne în git)",
           "exports": "exporturi citibile de om ale depozitului"},
}


def _cadence(sch, lang):
    if not isinstance(sch, dict):
        return ""
    units = {"en": {"h": ("hour", "hours"), "m": ("minute", "minutes"), "d": ("day", "days")},
             "ro": {"h": ("oră", "ore"), "m": ("minut", "minute"), "d": ("zi", "zile")}}[lang]
    seg = []
    if "every" in sch:
        v = str(sch["every"]).strip()
        num, unit = v[:-1], v[-1:]
        sing, plur = units.get(unit, (unit, unit))
        if num in ("", "1"):
            seg.append({"en": f"every {sing}", "ro": f"în fiecare {sing}"}[lang])
        else:
            seg.append({"en": f"every {num} {plur}", "ro": f"la fiecare {num} {plur}"}[lang])
    elif "monthly_on" in sch:
        d = sch["monthly_on"]
        suf = {1: "st", 2: "nd", 3: "rd"}.get(d if isinstance(d, int) and d < 20 else
                                              (d % 10 if isinstance(d, int) else 0), "th")
        seg.append({"en": f"on the {d}{suf} of each month",
                    "ro": f"lunar, pe data de {d}"}[lang])
    elif "daily_at" in sch:
        seg.append({"en": f"daily at {sch['daily_at']}", "ro": f"zilnic la {sch['daily_at']}"}[lang])
    elif "weekly_on" in sch:
        seg.append({"en": f"weekly on {sch['weekly_on']}", "ro": f"săptămânal ({sch['weekly_on']})"}[lang])
    win = sch.get("between")
    if win and "-" in str(win):
        a, b = str(win).split("-", 1)
        seg.append({"en": f"{a} to {b}", "ro": f"{a} - {b}"}[lang])
    return ", ".join(seg)


def _schedule_note(lang):
    """Build the 'Live today' note from the live schedule.yaml (user data). None
    on a fresh/wiped install (no schedule) -> the caller uses _SCHED_FALLBACK."""
    try:
        from tools._lib import userdata
        sdir = Path(userdata.schedule_dir())
    except Exception:
        return None
    entries = []
    try:
        if sdir.exists():
            for yf in sorted(sdir.glob("*.yaml")):
                doc = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                for e in (doc.get("entries") or []):
                    if e.get("enabled", True):
                        entries.append(e)
    except Exception:
        return None
    modes = {"en": {"driver": "driver mode", "auto": "auto mode"},
             "ro": {"driver": "mod driver", "auto": "mod auto"}}[lang]
    phrases = []
    for e in entries:
        tgt = e.get("target") or {}
        name, kind = tgt.get("name"), tgt.get("type", "agent")
        if not name or kind not in ("agent", "tool"):
            continue
        span = f'<span class="jump {kind}" data-ujump="{name}" data-ukind="{kind}">{name}</span>'
        cad = _cadence(e.get("schedule") or {}, lang)
        mode = modes.get(e.get("mode", "auto"), e.get("mode", "auto"))
        phrases.append(f"{span} {cad}, {mode}." if cad else f"{span}, {mode}.")
    if not phrases:
        return None
    n = len(phrases)
    lead = {"en": f"<b>Live today:</b> {n} job{'s' if n != 1 else ''} run on the hourly tick. ",
            "ro": f"<b>Activ azi:</b> {n} job{'uri' if n != 1 else ''} rulează pe tick-ul orar. "}[lang]
    return lead + " ".join(phrases)


def _store_tree(lang):
    """The context-state-knowledge tree, from the CANONICAL folder list.

    This used to read the REAL top-level folders off disk when present, so that a
    new subfolder was never omitted. But this panel documents the framework's
    LAYOUT - the folders the resolvers create - not any one installation of it,
    and framework-map.html is versioned: a checkout with user data produced
    different bytes than a clean one, so every builder generated a spurious diff
    over one person's folder set. (The "Live today" schedule note below IS
    deliberately live - showing the real jobs is the point of that panel. The
    difference is that the note announces itself as live, while this tree silently
    drifted per machine.)

    The "never omit a new subfolder" guarantee moves to test_fm_store_tree.py,
    which creates a user-data root through tools/_lib/userdata and asserts this
    list matches what the resolvers actually make - a build-time check instead of
    a read of one machine's disk. store.db's record types stay conceptual - they
    are DB types, not folders."""
    S = fm_strings.S[lang]
    folders = list(_CANON_FOLDERS)
    fdesc = {"config": S["tc_config"], "sessions": S["tc_sessions"],
             "schedule": S["tc_schedule"], **_FOLDER_EXTRA[lang]}
    out = [f'<span class="c">{S["tc_hdr"]}</span>', "context-state-knowledge/",
           f'&#9500;&#9472; <span class="d">store.db</span>{" " * 8}<span class="c">{S["tc_db"]}</span>']
    rt = [("knowledge", "tc_know"), ("resource", "tc_res"), ("preference", "tc_pref"),
          ("decision", "tc_dec"), ("runs", "tc_runs")]
    for i, (nm, key) in enumerate(rt):
        br = "&#9492;&#9472;" if i == len(rt) - 1 else "&#9500;&#9472;"
        out.append(f'&#9474;   {br} <span class="f">{nm}</span>{" " * (12 - len(nm))}'
                   f'<span class="c">{S[key]}</span>')
    for i, fn in enumerate(folders):
        br = "&#9492;&#9472;" if i == len(folders) - 1 else "&#9500;&#9472;"
        lbl = fn + "/"
        out.append(f'{br} <span class="d">{lbl}</span>{" " * max(2, 14 - len(lbl))}'
                   f'<span class="c">{fdesc.get(fn, "")}</span>')
    return "\n".join(out)


# Copy for GENERIC_HERO, carried here rather than in the per-install strings file
# so that ANY distribution renders a correct hero with nothing to author. A
# distribution that ships its own narrative overrides these from fm_strings.
GENERIC_HERO_STRINGS = {
    "en": {"w_tools": "tools", "w_agents": "agents", "w_skills": "skills",
           "w_actions": "actions",
           "hero_h": "Agents &amp; Tools",
           "hero_p": "Everything installed in this checkout, read straight from the "
                     "manifests. Search it, filter by category, and open any component "
                     "to see the actions it exposes and the credentials it needs."},
    "ro": {"w_tools": "unelte", "w_agents": "agen&#539;i", "w_skills": "skill-uri",
           "w_actions": "ac&#539;iuni",
           "hero_h": "Agen&#539;i &#537;i unelte",
           "hero_p": "Tot ce e instalat &#238;n acest checkout, citit direct din "
                     "manifeste. Caut&#259;, filtreaz&#259; pe categorii &#537;i deschide "
                     "orice component&#259; ca s&#259; vezi ce ac&#539;iuni expune &#537;i "
                     "ce creden&#539;iale &#238;i trebuie."},
}

def _fill(tpl: str, lang: str) -> str:
    svg = Template(SVG).safe_substitute(fm_strings.S[lang])
    # marker ids must be unique per language SVG, else url(#id) resolves to the
    # first (EN) marker, which is display:none in RO mode -> arrowheads vanish.
    for mid in ("ah", "ahg", "ahs"):
        svg = svg.replace('id="%s"' % mid, 'id="%s-%s"' % (mid, lang))
        svg = svg.replace('url(#%s)' % mid, 'url(#%s-%s)' % (mid, lang))
    # Fallback layer first, so a distribution that authors its own copy wins.
    d = dict(GENERIC_HERO_STRINGS[lang]); d.update(fm_strings.S[lang]); d["SVG"] = svg
    # Only build a panel the template actually asks for. Both helpers need copy
    # from the per-install strings file, and computing them unconditionally made
    # the engine fail on any distribution that does not render those sections.
    if "$sched_note" in tpl:
        d["sched_note"] = _schedule_note(lang) or _SCHED_FALLBACK[lang]
    if "$store_tree" in tpl:
        d["store_tree"] = _store_tree(lang)
    return Template(tpl).safe_substitute(d)


def _lang_div(inner: str, lang: str) -> str:
    return '<div class="lang lang-%s">%s</div>' % (lang, inner)


def assemble(data_en: dict, data_ro: dict, counts: dict) -> str:
    css = (TOOL_ROOT / "styles.css").read_text(encoding="utf-8")
    js = (TOOL_ROOT / "app.js").read_text(encoding="utf-8")
    dj = json.dumps(data_en, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    dro = json.dumps(data_ro, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    lbl = json.dumps(fm_strings.LBL, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    body = HEADER + '<main class="wrap">'
    body += _lang_div(_fill(PART_A, "en"), "en")
    body += _lang_div(_fill(PART_A, "ro"), "ro")
    body += EXPLORE
    body += _lang_div(_fill(PART_B, "en"), "en")
    body += _lang_div(_fill(PART_B, "ro"), "ro")
    body += '</main>'
    body += '<footer class="wrap">'
    body += _lang_div(Template("<div>$footer</div>").safe_substitute(fm_strings.S["en"]), "en")
    body += _lang_div(Template("<div>$footer</div>").safe_substitute(fm_strings.S["ro"]), "ro")
    body += '</footer>'

    for tok, val in [("$NTOOLS", "{:,}".format(counts["tools"])),
                     ("$NAGENTS", "{:,}".format(counts["agents"])),
                     ("$NSKILLS", "{:,}".format(counts["skills"])),
                     ("$NACTIONS", "{:,}".format(counts["actions"])),
                     ("$NTOOLACTIONS", "{:,}".format(counts["tool_actions"]))]:
        body = body.replace(tok, val)

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>Agents &amp; Tools &mdash; Framework Map</title>\n"
        "<style>" + css + "</style>\n</head>\n<body>\n"
        + body +
        "\n<script>const DATA=" + dj + ";const DATA_RO=" + dro + ";const LBL=" + lbl + ";</script>\n"
        "<script>\n" + js + "\n</script>\n</body>\n</html>"
    )


# ---- top-level orchestration -------------------------------------------------
def build_html(framework_root: Path):
    """Return (html_str, stats_dict)."""
    dump = extract(framework_root)
    data = compress(dump)
    data_ro, miss = translate_ro(data)
    tool_actions = sum(len(t["actions"]) for t in data["tools"])
    agent_actions = sum(len(a["actions"]) for a in data["agents"])
    counts = {
        "tools": len(data["tools"]), "agents": len(data["agents"]), "skills": len(data["skills"]),
        "tool_actions": tool_actions, "agent_actions": agent_actions,
        "actions": tool_actions + agent_actions,
    }
    html = assemble(data, data_ro, counts)
    stats = {
        **counts,
        "categories": categories(data),
        "uncategorized": uncategorized(data),
        "ro_untranslated": miss,
    }
    return html, stats


def stats_only(framework_root: Path):
    dump = extract(framework_root)
    data = compress(dump)
    _, miss = translate_ro(data)
    tool_actions = sum(len(t["actions"]) for t in data["tools"])
    agent_actions = sum(len(a["actions"]) for a in data["agents"])
    return {
        "tools": len(data["tools"]), "agents": len(data["agents"]), "skills": len(data["skills"]),
        "tool_actions": tool_actions, "agent_actions": agent_actions,
        "actions": tool_actions + agent_actions,
        "categories": categories(data), "uncategorized": uncategorized(data),
        "ro_untranslated": miss,
    }
