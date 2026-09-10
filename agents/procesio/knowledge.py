"""Load the agent's knowledge base (the markdown docs in this folder).

The `guidance` action serves these so any session/LLM loads the methodology from
ONE registry-discoverable place instead of re-deriving it. The docs are the
source of truth; this module just reads them.
"""
from __future__ import annotations

from pathlib import Path

KB_DIR = Path(__file__).resolve().parent

# The form-building guide lives beside the TOOL it documents (form DTO, event config,
# field paths), not in this folder. Serving it from here rather than copying it keeps
# one source of truth: a 100 KB guide duplicated into the agent would be stale within a
# release, and the version the model reads is the one that would be wrong.
FORM_GUIDE = KB_DIR.parents[1] / "tools" / "procesio" / "FORM-DEV-GUIDE"

# topic -> (path relative to KB_DIR, or an absolute Path; human label)
TOPICS: dict[str, tuple[str | Path, str]] = {
    "playbook": ("PROCESIO-BUILD-AND-TEST-PLAYBOOK.md",
                 "Build-and-test operating procedure"),
    "best-practices": ("PROCESIO-BEST-PRACTICES.md",
                       "PROCESIO implementation best practices"),
    "visual-organization": ("PROCESIO-VISUAL-ORGANIZATION.md",
                            "Visual canvas layout + recurring build patterns"),
    "datastore": ("PROCESIO-DATASTORE.md",
                  "Data Store module: API actions, process node, form trigger"),
    "scheduling": ("PROCESIO-SCHEDULING.md",
                   "Scheduling a process (recurrences + crontab)"),
    "environments": ("PROCESIO-ENVIRONMENTS.md",
                     "Working across PROCESIO environments (switch/add <Client>-<ENV>)"),
    "reliability": ("PROCESIO-API-RELIABILITY-DOCTRINE.md",
                    "Driving the PROCESIO Web API safely: sequential calls, "
                    "behavioural verification, deadlines/retries, form-build traps"),
    "boundary": ("README.md", "Agent knowledge base + tool-vs-agent boundary"),

    # Building a FORM is a different discipline from building a process, and asking for
    # it returned `unknown topic` - so an agent that needed the field-path shape, the
    # event contract or the known traps had no way to reach the guide that documents
    # all three. Measured cost of that gap in one run: a RUN_PROCESS map written with
    # invented paths ("root.fields.<id>.value" instead of the four-GUID chain) and the
    # two sides transposed, which the API accepts silently and which binds nothing.
    #
    # Served as ONE entry per guide file rather than a single `forms` blob: the guide is
    # ~100 KB, over the character budget a run carries forward, so a single topic would
    # be an answer no step could keep. `forms` is the index, which names the rest.
    "forms": (FORM_GUIDE / "00-INDEX.md",
              "Form development guide - START HERE, names the sub-topics below"),
    "forms-anatomy": (FORM_GUIDE / "01-ANATOMY.md",
                      "Form anatomy: elements, config ids, the field VALUE PATH"),
    "forms-code": (FORM_GUIDE / "02-CODE-INJECTION.md",
                   "Injecting custom code into a form"),
    "forms-dom": (FORM_GUIDE / "03-DOM-CONTRACT.md",
                  "The rendered DOM contract a form's code may rely on"),
    "forms-interaction": (FORM_GUIDE / "04-INTERACTION-RECIPES.md",
                          "Interaction recipes: show/hide, validation, computed fields"),
    "forms-motion": (FORM_GUIDE / "05-STEPPER-AND-MOTION.md",
                     "Multi-step forms (stepper) and motion"),
    "forms-process": (FORM_GUIDE / "06-PROCESS-INTEGRATION.md",
                      "Wiring a control to a process: RUN_PROCESS event, inputMap/"
                      "outputMap row shape, form value paths"),
    "forms-deploy": (FORM_GUIDE / "07-DEPLOY-WORKFLOW.md",
                     "Publishing a form and its custom URL"),
    "forms-pitfalls": (FORM_GUIDE / "08-PITFALLS.md",
                       "Known form traps and their signatures"),
}

# `topic=all` concatenates everything it lists, so the form guide's chapters stay out of
# it: they would multiply that payload sixfold and bury the process guidance most callers
# actually asked for. The `forms` index IS included - it is small and it advertises the
# chapters, which is exactly what a caller who did not know they existed needs.
_ALL_EXCLUDED = {t for t in TOPICS if t.startswith("forms-")}


def topics() -> list[str]:
    return list(TOPICS.keys())


def load(topic: str) -> dict:
    if topic not in TOPICS:
        raise KeyError(
            f"unknown topic: {topic}. Known: {', '.join(TOPICS)}")
    filename, label = TOPICS[topic]
    path = filename if isinstance(filename, Path) else KB_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"knowledge file missing: {path}")
    return {
        "topic": topic,
        "label": label,
        "source": str(path),
        "content": path.read_text(encoding="utf-8"),
    }


def load_all() -> list[dict]:
    """Every topic that belongs in a `topic=all` answer (see _ALL_EXCLUDED)."""
    return [load(t) for t in TOPICS if t not in _ALL_EXCLUDED]
