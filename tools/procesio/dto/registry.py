"""Registry of DTO components. Explicit (no import magic) for reliability —
add a component's COMPONENT here and it gets <name>-create / <name>-edit actions.
"""
from __future__ import annotations

from functools import lru_cache

from tools.procesio.dto.framework import Component


@lru_cache(maxsize=1)
def all_components() -> dict[str, Component]:
    from tools.procesio.dto.credential import builder as credential
    from tools.procesio.dto.datatype import builder as datatype
    from tools.procesio.dto.document import builder as document
    from tools.procesio.dto.form import builder as form
    from tools.procesio.dto.process import builder as process
    from tools.procesio.dto.webhook import builder as webhook
    comps = [
        datatype.COMPONENT,
        process.COMPONENT,
        credential.COMPONENT,
        document.COMPONENT,
        webhook.COMPONENT,
        form.COMPONENT,
    ]
    return {c.name: c for c in comps}
