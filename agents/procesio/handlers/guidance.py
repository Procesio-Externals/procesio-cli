"""guidance action - serve the agent's knowledge base (the build-and-test
playbook, best practices, and the tool-vs-agent boundary) from one
registry-discoverable place. The methodology is loaded, never re-derived.
"""
from __future__ import annotations

import argparse

from agents._lib.actiondef import ActionDef
from agents._lib.errors import AgentError
from agents.procesio import knowledge


def _guidance(args) -> dict:
    if args.topic == "all":
        return {"topics": knowledge.topics(), "sections": knowledge.load_all()}
    try:
        return knowledge.load(args.topic)
    except (KeyError, FileNotFoundError) as e:
        raise AgentError("unknown_topic", str(e),
                         {"known": knowledge.topics() + ["all"]})


def _args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--topic", default="all",
                   help="playbook | best-practices | visual-organization | datastore | "
                        "scheduling | environments | boundary | all (default all)")


ACTIONS = {
    "guidance": ActionDef(
        func=_guidance, add_args=_args,
        description="Serve the build-and-test playbook + best practices (the agent's "
                    "knowledge base). --topic playbook|best-practices|"
                    "visual-organization|boundary|all."),
}
