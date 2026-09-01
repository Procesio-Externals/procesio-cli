"""Load the agent's knowledge base (the markdown docs in this folder).

The `guidance` action serves these so any session/LLM loads the methodology from
ONE registry-discoverable place instead of re-deriving it. The docs are the
source of truth; this module just reads them.
"""
from __future__ import annotations

from pathlib import Path

KB_DIR = Path(__file__).resolve().parent

# topic -> (filename, human label)
TOPICS: dict[str, tuple[str, str]] = {
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
}


def topics() -> list[str]:
    return list(TOPICS.keys())


def load(topic: str) -> dict:
    if topic not in TOPICS:
        raise KeyError(
            f"unknown topic: {topic}. Known: {', '.join(TOPICS)}")
    filename, label = TOPICS[topic]
    path = KB_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"knowledge file missing: {path}")
    return {
        "topic": topic,
        "label": label,
        "source": str(path),
        "content": path.read_text(encoding="utf-8"),
    }


def load_all() -> list[dict]:
    return [load(t) for t in TOPICS]
