from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import ExternalSource
from .storage import ExternalStorage


DEFAULT_SOURCES = (
    ExternalSource("archive-org-amiga-cdrom", "Amiga CD-ROM collection", "Broad Amiga CD-ROM metadata source", "internet-archive", "https://archive.org", "amiga_cdrom", "aminet-cd", ("amiga",), ("cdrom",), "unknown", "unknown"),
    ExternalSource("archive-org-softwarecapsules", "Software Capsules Commodore", "Commodore-related metadata source", "internet-archive", "https://archive.org", "softwarecapsules_commodore", "unknown", ("amiga", "commodore"), ("software",), "unknown", "unknown"),
    ExternalSource("archive-org-aminetcd", "Aminet CDs", "Aminet CD image metadata source", "internet-archive", "https://archive.org", "aminetcd", "aminet-cd", ("amiga",), ("aminet", "cdrom"), "unknown", "unknown"),
    ExternalSource("archive-org-fred-fish", "Fred Fish collections", "Fred Fish preservation metadata source", "internet-archive", "https://archive.org", "commodore-amiga-collections-fred-fish", "fred-fish", ("amiga",), ("fred-fish",), "unknown", "unknown"),
)


def validate_source(source: ExternalSource) -> None:
    if source.provider_type != "internet-archive":
        raise ValueError(f"unsupported external provider: {source.provider_type}")
    if not source.locator.startswith("https://archive.org"):
        raise ValueError("Internet Archive sources must use the official HTTPS endpoint")
    if source.inspection_policy not in {"metadata-only"}:
        raise ValueError("unsupported inspection policy")


class ExternalSourceStore:
    def __init__(self, metadata_root: Path):
        self.storage = ExternalStorage(metadata_root)

    def save(self, source: ExternalSource) -> Path:
        validate_source(source)
        if any(item.get("id") == source.id for item in self.storage.list("external-sources")):
            raise ValueError(f"external source already exists: {source.id}")
        return self.storage.put("external-sources", source.id, source)

    def upsert(self, source: ExternalSource) -> Path:
        validate_source(source)
        return self.storage.put("external-sources", source.id, source)

    def get(self, source_id: str) -> ExternalSource:
        return ExternalSource(**self.storage.get("external-sources", source_id))

    def list(self) -> tuple[ExternalSource, ...]:
        return tuple(ExternalSource(**item) for item in self.storage.list("external-sources"))

    def seed_defaults(self) -> None:
        for source in DEFAULT_SOURCES:
            if not any(item.id == source.id for item in self.list()):
                self.upsert(source)
