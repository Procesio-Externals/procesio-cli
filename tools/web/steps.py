"""Declarative step interpreter for the web tool's ``run`` action.

A *step list* is a JSON array of step objects. Each step has a ``do`` key
selecting the operation; the remaining keys are its parameters. The interpreter
dispatches each step to one ``BrowserDriver`` call, collecting named outputs.

Step schema (mini-language)
---------------------------
  {"do": "goto",         "url": "https://..."[, "timeout": ms]}
  {"do": "click",        "selector": "css-or-text"[, "timeout": ms][, "force": true]}
  {"do": "fill",         "selector": "...", "text": "..."[, "timeout": ms]}
  {"do": "press",        "key": "Enter"[, "selector": "..."]}
  {"do": "type",         "text": "...", "selector": "..."(optional)[, "timeout": ms]}
  {"do": "wait",         "ms": 1500}
  {"do": "wait_for",     "selector": "..."[, "timeout": ms]}
  {"do": "extract_text", "selector": "..."(optional), "name": "field"[, "timeout": ms]}
  {"do": "extract_attr", "selector": "...", "attr": "href", "name": "field"[, "timeout": ms]}
  {"do": "screenshot",   "path": "out.png"[, "full_page": true]}
  {"do": "upload",       "selector": "input[type=file]", "path": "a.png" | ["a.png", ...][, "timeout": ms]}
  {"do": "upload_via_chooser", "selector": "button.attach", "path": "a.png" | [...][, "timeout": ms]}

``upload`` sets files on an ``<input type=file>`` directly (the input may be
hidden - the standard Playwright way). ``upload_via_chooser`` is for a site whose
real file input exists only transiently behind a NATIVE chooser: it clicks the
trigger selector while expecting the chooser, then hands it the files. ``path``
is a single path string or a list of paths.

Return value
------------
``run_steps(driver, steps)`` returns
    {"results": {name -> value}, "screenshots": [path, ...], "final_url": "..."}

``extract_text`` / ``extract_attr`` write into ``results`` under their ``name``
(falling back to the selector if no name is given). ``screenshot`` paths are
collected into ``screenshots``.

The interpreter validates each step *before* touching the driver, raising
``UsageError`` (-> invalid_argument, exit 2) on a malformed step. This means a
bad step list fails fast and identically whether or not a real browser exists.
"""
from __future__ import annotations

from typing import Any

from tools.web.errors import UsageError

# do-name -> required keys (besides "do") and optional keys it understands.
_SCHEMA: dict[str, dict[str, set[str]]] = {
    "goto": {"required": {"url"}, "optional": {"timeout"}},
    "click": {"required": {"selector"}, "optional": {"timeout", "force"}},
    "fill": {"required": {"selector", "text"}, "optional": {"timeout"}},
    "press": {"required": {"key"}, "optional": {"selector"}},
    "type": {"required": {"text"}, "optional": {"selector", "timeout"}},
    "wait": {"required": {"ms"}, "optional": set()},
    "wait_for": {"required": {"selector"}, "optional": {"timeout"}},
    "extract_text": {"required": set(), "optional": {"selector", "name", "timeout"}},
    "extract_attr": {"required": {"selector", "attr"}, "optional": {"name", "timeout"}},
    "eval": {"required": {"script"}, "optional": {"name", "arg"}},
    "screenshot": {"required": {"path"}, "optional": {"full_page"}},
    "upload": {"required": {"selector", "path"}, "optional": {"timeout"}},
    "upload_via_chooser": {"required": {"selector", "path"}, "optional": {"timeout"}},
}

KNOWN_STEPS = frozenset(_SCHEMA)


def _validate_step(i: int, step: Any) -> tuple[str, dict]:
    if not isinstance(step, dict):
        raise UsageError(f"step {i}: must be a JSON object, got {type(step).__name__}")
    do = step.get("do")
    if not do:
        raise UsageError(f"step {i}: missing 'do' key")
    if do not in _SCHEMA:
        raise UsageError(
            f"step {i}: unknown action {do!r}. Known: {', '.join(sorted(_SCHEMA))}"
        )
    spec = _SCHEMA[do]
    keys = set(step) - {"do"}
    missing = spec["required"] - keys
    if missing:
        raise UsageError(f"step {i} ({do}): missing required key(s): {', '.join(sorted(missing))}")
    allowed = spec["required"] | spec["optional"]
    extra = keys - allowed
    if extra:
        raise UsageError(f"step {i} ({do}): unknown key(s): {', '.join(sorted(extra))}")
    return do, step


def validate_steps(steps: Any) -> list[tuple[str, dict]]:
    """Validate a whole step list without running it. Raises UsageError."""
    if not isinstance(steps, list):
        raise UsageError("steps must be a JSON array of step objects")
    return [_validate_step(i, s) for i, s in enumerate(steps)]


def _timeout(step: dict) -> int | None:
    t = step.get("timeout")
    return int(t) if t is not None else None


def run_steps(driver, steps: Any) -> dict:
    """Execute a validated step list against a BrowserDriver.

    Returns {"results": {...}, "screenshots": [...], "final_url": "..."}.
    """
    validated = validate_steps(steps)
    results: dict[str, Any] = {}
    screenshots: list[str] = []

    for do, step in validated:
        if do == "goto":
            driver.goto(step["url"], timeout=_timeout(step))
        elif do == "click":
            driver.click(step["selector"], timeout=_timeout(step),
                         force=bool(step.get("force")))
        elif do == "fill":
            driver.fill(step["selector"], step["text"], timeout=_timeout(step))
        elif do == "press":
            driver.press(step["key"], selector=step.get("selector"))
        elif do == "type":
            driver.type_text(step["text"], selector=step.get("selector"),
                             timeout=_timeout(step))
        elif do == "wait":
            driver.wait(int(step["ms"]))
        elif do == "wait_for":
            driver.wait_for(step["selector"], timeout=_timeout(step))
        elif do == "extract_text":
            name = step.get("name") or step.get("selector") or "text"
            results[name] = driver.extract_text(
                step.get("selector"), timeout=_timeout(step)
            )
        elif do == "extract_attr":
            name = step.get("name") or f"{step['selector']}@{step['attr']}"
            results[name] = driver.extract_attr(
                step["selector"], step["attr"], timeout=_timeout(step)
            )
        elif do == "eval":
            # evaluate JS in the page and collect the result — for verification asserts
            # that need live DOM/JS state (e.g. an input's .value PROPERTY, which
            # extract_attr cannot read). {"do":"eval","script":"...","name":"key"}
            name = step.get("name") or "eval"
            results[name] = driver.eval_js(step["script"], arg=step.get("arg"))
        elif do == "screenshot":
            path = driver.screenshot(
                step["path"], full_page=bool(step.get("full_page", True))
            )
            screenshots.append(path)
        elif do == "upload":
            driver.set_input_files(step["selector"], step["path"], timeout=_timeout(step))
        elif do == "upload_via_chooser":
            driver.set_files_via_chooser(step["selector"], step["path"], timeout=_timeout(step))

    out: dict[str, Any] = {"results": results, "screenshots": screenshots}
    try:
        out["final_url"] = driver.current_url()
    except Exception:  # noqa: BLE001 - current_url is best-effort metadata
        pass
    return out
