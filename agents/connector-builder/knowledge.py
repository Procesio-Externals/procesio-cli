"""Load the agent's knowledge base (the markdown in this folder).

The `guidance` action serves these so any session loads the methodology from ONE
registry-discoverable place instead of re-deriving it. The docs are the source of
truth; this module just reads them.
"""
from __future__ import annotations

from pathlib import Path

KB_DIR = Path(__file__).resolve().parent

# topic -> (filename, human label)
TOPICS: dict[str, tuple[str, str]] = {
    "playbook": ("CONNECTOR-BUILDER-PLAYBOOK.md",
                 "Build → upload → test → improve operating procedure"),
    "interop": ("CONNECTOR-BUILDER-PROCESIO-INTEROP.md",
                "How this agent hands off to the procesio tool/agent"),
    "troubleshooting": ("CONNECTOR-BUILDER-TROUBLESHOOTING.md",
                        "Operations: tool/skill inventory, live-run realities, failure "
                        "triage (NU1301 vs code), definition of done"),
    "boundary": ("README.md",
                 "Agent overview + tool-vs-agent boundary"),
}


def topics() -> list[str]:
    return list(TOPICS.keys())


def load(topic: str) -> dict:
    if topic not in TOPICS:
        raise KeyError(f"unknown topic: {topic}. Known: {', '.join(TOPICS)}")
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
