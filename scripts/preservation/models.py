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
    license_profile: str = "unknown"
    media_classification: str = "unknown"
    notes: str = ""


@dataclass(frozen=True)
class MediaRecord:
    id: str
    title: str
    original_filename: str
    size: int
    hashes: Hashes
    license_profile: str = "unknown"
    media_classification: str = "unknown"
    edition: str = ""
    version: str = ""
    publisher: str = ""
    release_year: int | None = None
    source_id: str = ""
    original_path: str = ""
    imported_at: str = ""
    notes: str = ""
    redistributable: bool = False
    export_allowed: bool = False


@dataclass(frozen=True)
class ImportTransaction:
    id: str
    source_id: str
    source_fingerprint: str
    destination_collection: str
    operation: str
    started_at: str
    updated_at: str
    phase: str
    completed_entries: tuple[str, ...] = field(default_factory=tuple)
    pending_entries: tuple[str, ...] = field(default_factory=tuple)
    failed_entries: tuple[str, ...] = field(default_factory=tuple)
    conflict_entries: tuple[str, ...] = field(default_factory=tuple)
    result: str = ""


@dataclass(frozen=True)
class TransactionEntry:
    id: str
    transaction_id: str
    source_path: str
    target_path: str
    staging_path: str
    expected_hashes: Hashes | None = None
    observed_hashes: Hashes | None = None
    bytes_processed: int = 0
    state: str = "pending"
    attempts: int = 0
    error: str = ""
    verification_event_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TransactionEvent:
    id: str
    transaction_id: str
    entry_id: str | None
    previous_state: str
    new_state: str
    phase: str
    operation: str
    timestamp: str
    result: str = ""


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
