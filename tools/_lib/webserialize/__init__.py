"""webserialize — per-tool serializing brokers for persistent web profiles.

Two processes driving the same browser profile concurrently corrupt/invalidate
the web app's session (Chromium SingletonLock). This lib gives each tool ONE
broker process that owns its profile and executes commands strictly one at a
time; clients (the tool's own dispatch, and the generic web tool) submit over
a tiny local JSONL protocol.

Reference integration: tools/whatsapp-personal (v0.2.0 originated the pattern,
now a thin adapter over this lib). Registry of brokers/ports/owned sessions:
tools/_lib/webserialize/registry.py.
"""
from tools._lib.webserialize.config import HOST, PROTO, BrokerConfig  # noqa: F401
from tools._lib.webserialize.errors import (  # noqa: F401
    ServiceError, ServiceRemoteError,
)
