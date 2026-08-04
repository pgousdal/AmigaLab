from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExternalSource:
    id: str
    name: str
    description: str
    provider_type: str
    locator: str
    upstream_identifier: str
    target: str
    platform_tags: tuple[str, ...] = ()
    content_tags: tuple[str, ...] = ()
    license_profile: str = "unknown"
    media_classification: str = "unknown"
    enabled: bool = True
    inspection_policy: str = "metadata-only"
    mirror_policy: str = "original-media"
    check_interval: str = ""
    last_successful_check: str = ""
    last_attempted_check: str = ""
    last_snapshot_id: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = 1


@dataclass(frozen=True)
class ExternalFile:
    name: str
    size: int | None = None
    format: str = ""
    classification: str = "unknown"
    md5: str = ""
    sha1: str = ""
    crc32: str = ""
    mtime: str = ""
    locator: str = ""
    restricted: bool = False
    upstream_hashes: str = "upstream-reported"


@dataclass(frozen=True)
class ExternalItem:
    identifier: str
    title: str = ""
    description: str = ""
    creator: str = ""
    date: str = ""
    subjects: tuple[str, ...] = ()
    media_type: str = ""
    collections: tuple[str, ...] = ()
    license_metadata: str = ""
    access: str = "public"
    locator: str = ""
    files: tuple[ExternalFile, ...] = ()


@dataclass(frozen=True)
class ExternalSnapshot:
    id: str
    source_id: str
    provider_type: str
    check_id: str
    captured_at: str
    collection_metadata: dict[str, object]
    items: tuple[ExternalItem, ...]
    warnings: tuple[str, ...] = ()
    completed: bool = True
    fingerprint: str = ""
    schema_version: int = 1


@dataclass(frozen=True)
class MirrorPlan:
    id: str
    source_id: str
    snapshot_id: str
    previous_snapshot_id: str
    created_at: str
    policy: str
    status: str
    selected_files: tuple[dict[str, object], ...]
    excluded_files: tuple[dict[str, object], ...]
    target_category: str
    warnings: tuple[str, ...] = ()
    blocking_issues: tuple[str, ...] = ()
    fingerprint: str = ""
    schema_version: int = 1
