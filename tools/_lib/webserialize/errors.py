"""Error classes for broker communication. Tools classify exceptions into
their JSON error envelopes BY CLASS NAME (see any tool's errors.py), so these
names — ``ServiceError`` and ``ServiceRemoteError`` — are part of the contract:

  ServiceError        -> code "service_error", exit 1 (client-side comms
                         failure AFTER submission; NEVER auto-retried — the
                         command may have executed inside the service)
  ServiceRemoteError  -> surfaced verbatim: the ORIGINAL code/message/details/
                         exit_code produced inside the service worker, so
                         service mode and direct mode fail identically.
"""
from __future__ import annotations


class ServiceError(Exception):
    """Client-side failure talking to the serializing service."""


class ServiceRemoteError(Exception):
    """An error envelope produced INSIDE the service worker, re-raised on the
    client. ``errors.classify`` in each tool unwraps it verbatim."""

    def __init__(self, code: str, message: str, details: dict, exit_code: int):
        self.code = code
        self.details = details or {}
        self.exit_code = exit_code
        super().__init__(message)
