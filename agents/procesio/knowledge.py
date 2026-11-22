"""Load the agent's knowledge base (the markdown docs in this folder).

The `guidance` action serves these so any session/LLM loads the methodology from
ONE registry-discoverable place instead of re-deriving it. The docs are the
source of truth; this module just reads them.
"""
from __future__ import annotations

import json
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent

# The form-building guide lives beside the TOOL it documents (form DTO, event config,
# field paths), not in this folder. Serving it from here rather than copying it keeps
# one source of truth: a 100 KB guide duplicated into the agent would be stale within a
# release, and the version the model reads is the one that would be wrong.
FORM_GUIDE = KB_DIR.parents[1] / "tools" / "procesio" / "FORM-DEV-GUIDE"

# The house style, distilled from auditing a production workspace: HOW this team builds,
# where the best-practices doc says WHAT good looks like. Served per file like the form
# guide (~80 KB together); `patterns` is the index and names the rest.
PATTERNS = KB_DIR / "IMPLEMENTATION-PATTERNS"

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
    "forms-redesign": (FORM_GUIDE / "10-REDESIGN-METHOD.md",
                       "Redesigning a form or a family of forms: order of work, patterns, shipping, verification, performance"),

    "patterns": (PATTERNS / "00-INDEX.md",
                 "House implementation patterns - START HERE, names the sub-topics + the "
                 "workspace-knowledge folder convention"),
    "patterns-processes": (PATTERNS / "01-PROCESSES.md",
                           "How we build processes: result flags, HTML rendering, Node idioms, utilities"),
    "patterns-forms": (PATTERNS / "02-FORMS.md",
                       "How we build forms and form<->process communication"),
    "patterns-integrations": (PATTERNS / "03-INTEGRATIONS.md",
                              "How we build integrations: webhooks, ERP, SFTP, LLM extraction, documents"),
    "patterns-database": (PATTERNS / "04-DATABASE.md",
                          "How we design tables and stored procedures for PROCESIO"),
    "patterns-optimizing": (PATTERNS / "05-OPTIMIZING-A-WORKSPACE.md",
                            "Changing a workspace someone else built: audit, speed, recoverable failures, safe rollout"),
}

# The SHAPE of the one `config` object that a whole-definition writer takes (process-create /
# process-edit, form-create / form-edit). A caller that reaches the writer through a named
# tool sees `config` as a bare object: the schema is too large to send with every model
# request, so it is served here, on demand, and the tool names this topic.
#
# Measured cost of a writer whose shape the caller cannot read: the caller guesses field
# names (`name` for `title`, `data_type` for `type`, `is_list` for `isList`) and learns the
# shape from validation errors, one layer per attempt.
#
# Generated, never written down: the schema is the file the component validates against and
# the example is the fixture its tests build, the same two the action's manifest publishes.
# A copy in a markdown file would drift from the code that refuses a config.
#
# topic -> (component folder under tools/procesio/dto, what the config builds, human label)
CONFIG_DIR = KB_DIR.parents[1] / "tools" / "procesio" / "dto"
CONFIG_TOPICS: dict[str, tuple[str, str, str]] = {
    "process-config": ("process", "process",
                       "The shape of the config that process-create and process-edit take: "
                       "the JSON Schema and a config that works"),
    "form-config": ("form", "form",
                    "The shape of the config that form-create and form-edit take: "
                    "the JSON Schema and a config that works"),
}


def config_shape(topic: str) -> dict:
    """The schema and the worked example behind one config topic, as data.

    {"schema": <the component's config.schema.json>, "example": <its first fixture, or None>,
     "source": <the schema file>}. Raises KeyError for a topic that is not a config topic."""
    folder, _, _ = CONFIG_TOPICS[topic]
    schema_path = CONFIG_DIR / folder / "config.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"knowledge file missing: {schema_path}")
    example = None
    # The first fixture in name order: the rule the manifest uses for its own example.
    for fixture in sorted((CONFIG_DIR / folder / "fixtures").glob("*.config.json")):
        example = json.loads(fixture.read_text(encoding="utf-8"))
        break
    return {"schema": json.loads(schema_path.read_text(encoding="utf-8")),
            "example": example, "source": schema_path}


def _config_content(topic: str, shape: dict) -> str:
    _, what, _ = CONFIG_TOPICS[topic]
    parts = [
        f"# The `config` of a {what}",
        "",
        f"The create and the edit action of a {what} take ONE JSON object, `config`, in the "
        "shape below. Use the property names exactly as the schema spells them: where the "
        "schema says `additionalProperties: false`, a property it does not list is refused.",
        "",
        f"This is an authoring shape. It is NOT the object that reading a {what} returns from "
        "the platform, so do not send that object back as `config`.",
    ]
    if shape["example"] is not None:
        parts += ["", "## A config that works", "", "```json",
                  json.dumps(shape["example"], ensure_ascii=False, indent=2), "```"]
    parts += ["", "## The schema", "", "```json",
              json.dumps(shape["schema"], ensure_ascii=False, separators=(",", ":")), "```", ""]
    return "\n".join(parts)


# `topic=all` concatenates everything it lists, so the form guide's chapters stay out of
# it: they would multiply that payload sixfold and bury the process guidance most callers
# actually asked for. The `forms` index IS included - it is small and it advertises the
# chapters, which is exactly what a caller who did not know they existed needs.
_ALL_EXCLUDED = {t for t in TOPICS if t.startswith(("forms-", "patterns-"))}
# The config shapes are never in `all` either (they are not in TOPICS): each is ten kilobytes
# of schema that only a caller about to write that one object needs.


def topics() -> list[str]:
    return list(TOPICS.keys()) + list(CONFIG_TOPICS.keys())


def load(topic: str) -> dict:
    if topic in CONFIG_TOPICS:
        shape = config_shape(topic)
        return {
            "topic": topic,
            "label": CONFIG_TOPICS[topic][2],
            "source": str(shape["source"]),
            "content": _config_content(topic, shape),
        }
    if topic not in TOPICS:
        raise KeyError(
            f"unknown topic: {topic}. Known: {', '.join(topics())}")
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
