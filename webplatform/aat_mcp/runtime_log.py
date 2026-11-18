"""One writer for every log line of the MCP servers, in one of two formats.

`text` (the default) is a line a person reads at a terminal: `[source] the sentence`. It is
what a local run and the stdio servers write.

`json` is one JSON object per line, for a log store. Its keys are the ones the .NET services
of the same product write, so one query reads all of them:

    {"Timestamp": "...+00:00", "Level": "Information", "RenderedMessage": "the sentence",
     "Properties": {"SourceContext": "...", "MessageId": "...", ...}}

`RenderedMessage` is the same sentence the text format writes, so nothing is lost by switching.
`Properties` holds the values of that sentence one by one, for a filter that does not have to
parse it. A line that names a turn carries its id as `Properties.MessageId`, the key the other
services use for the same id.

The format is chosen by AAT_LOG_FORMAT, read at every write: the server can be started with
either, and a test can switch it. Everything goes to stderr - in stdio mode stdout carries the
JSON-RPC stream. Writing a line never raises: a log line is never worth a failed call.

Standard library only, and it imports nothing of this package.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

FORMAT_ENV = "AAT_LOG_FORMAT"
JSON, TEXT = "json", "text"

INFO, WARNING, ERROR = "Information", "Warning", "Error"

# The category of a line about one call of one turn: the same value the other services give
# their lines about a turn, so a search for the category finds the turn end to end.
TURN = "Procesio.Aat.Turn"


def json_format() -> bool:
    return (os.environ.get(FORMAT_ENV) or "").strip().lower() == JSON


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def render(source: str, text: str, *, level: str = INFO, category: str | None = None,
           fields: dict | None = None, exception: str | None = None) -> str:
    """The line `write` would write, without its newline."""
    if not json_format():
        return f"[{source}] {text}"
    properties = {"SourceContext": category or source}
    for key, value in (fields or {}).items():
        if value is not None:
            properties[key] = value
    record = {"Timestamp": _timestamp(), "Level": level, "RenderedMessage": text}
    if exception:
        record["Exception"] = exception
    record["Properties"] = properties
    # default=str: a value of a type JSON has no word for is written as its text, not refused.
    return json.dumps(record, ensure_ascii=False, default=str)


def write(source: str, text: str, *, level: str = INFO, category: str | None = None,
          fields: dict | None = None, exception: str | None = None) -> None:
    """Write one log line. `source` names the part of the server that writes it: it is the
    prefix of a text line, and the category of a JSON line unless `category` names one.
    `fields` become `Properties` of a JSON line (a None value is left out) and are not written
    in the text format, whose sentence already says them. One write, so the lines of concurrent
    requests do not interleave."""
    try:
        sys.stderr.write(render(source, text, level=level, category=category, fields=fields,
                                exception=exception) + "\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
