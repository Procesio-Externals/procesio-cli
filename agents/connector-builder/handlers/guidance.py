"""guidance action — serve the agent's operating doctrine from one place.

Loads the playbook / interop / boundary markdown so a session reads the
methodology instead of re-deriving it. Pure file read; no live calls.
"""
from __future__ import annotations

import argparse

from agents._lib.actiondef import ActionDef
from agents._lib.errors import AgentError

import knowledge


def _guidance(args) -> dict:
    topic = (args.topic or "all").strip().lower()
    if topic == "all":
        return {"topics": knowledge.topics(), "documents": knowledge.load_all()}
    try:
        return knowledge.load(topic)
    except KeyError as e:
        raise AgentError("unknown_topic", str(e),
                         {"known": knowledge.topics()}) from e


def _guidance_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--topic", default="all",
                   help="playbook | interop | boundary | all")


ACTIONS = {
    "guidance": ActionDef(
        func=_guidance, add_args=_guidance_args,
        description="Serve the build→test→improve playbook + PROCESIO interop doctrine.",
    ),
}
