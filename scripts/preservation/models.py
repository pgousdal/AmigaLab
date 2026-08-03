"""Dataclasses describing preserved objects and their independent metadata."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Hashes:
    md5: str
    sha1: str
    sha256: str
    sha512: str


@dataclass(frozen=True)
class PreservedFile:
    original_collection: str
    original_relative_path: str
    original_filename: str
    size: int
    modified_time_ns: int
    hashes: Hashes


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: str
    locator: str


@dataclass(frozen=True)
class ImportEvent:
    id: str
    timestamp: str
    source_id: str
    method: str
    tool_version: str
    result: str


@dataclass(frozen=True)
class VerificationEvent:
    id: str
    timestamp: str
    object_id: str
    algorithm: str
    success: bool
    failure_reason: str | None


@dataclass(frozen=True)
class PreservationObject:
    id: str
    original_collection: str
    original_relative_path: str
    files: tuple[PreservedFile, ...]
    provenance_source_ids: tuple[str, ...] = field(default_factory=tuple)
    import_event_ids: tuple[str, ...] = field(default_factory=tuple)
    verification_event_ids: tuple[str, ...] = field(default_factory=tuple)
