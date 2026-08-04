"""Deterministic completion obligations for transaction entries."""

from __future__ import annotations


def required_obligations(operation: str, import_mode: str) -> tuple[str, ...]:
    if operation == "preserve-media" or import_mode == "media-only":
        return ("destination", "media-metadata", "import-event", "verification-event")
    return ("destination", "object-metadata", "provenance", "import-event", "verification-event")
