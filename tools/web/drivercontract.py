"""Check a test double against the BrowserDriver contract.

Several tools drive a browser through `tools/web/steps.run_steps`, and each
keeps its own `FakeDriver` test double. When the real driver gains a parameter -
`click(..., force=...)` was the one that bit - every double that does not accept
it starts raising TypeError, and the break surfaces in an unrelated tool's suite
hours later, looking like that tool's bug.

A double is deliberately allowed to implement only the subset of methods its own
tests exercise. What it may NOT do is implement a method with a signature the
step runner cannot call. That is the only thing checked here.
"""
from __future__ import annotations

import inspect

from tools.web.driver import BrowserDriver


def signature_mismatches(double: type) -> list[str]:
    """Parameters BrowserDriver defines that `double` could not accept.

    Returns one readable line per problem, empty when the double is callable
    everywhere the real driver is. A double taking **kwargs is exempt: it can
    absorb anything, at the cost of not asserting on it.
    """
    problems: list[str] = []
    for name, proto_fn in inspect.getmembers(BrowserDriver, inspect.isfunction):
        if name.startswith("_"):
            continue
        fake_fn = getattr(double, name, None)
        if fake_fn is None:
            continue  # implementing a subset is fine
        fake_params = inspect.signature(fake_fn).parameters
        if any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in fake_params.values()):
            continue
        for pname in inspect.signature(proto_fn).parameters:
            if pname == "self" or pname in fake_params:
                continue
            problems.append(
                f"{double.__name__}.{name}() cannot accept {pname!r}, which "
                f"BrowserDriver.{name}() defines")
    return problems
