from __future__ import annotations
from dataclasses import dataclass, asdict, field
from .fingerprints import document_fingerprint


@dataclass(frozen=True)
class CatalogDocument:
    id: str
    entity_type: str
    canonical_id: str
    collection: str = ""
    title: str = ""
    display_name: str = ""
    historical_filename: str = ""
    relative_path: str = ""
    parent_path: str = ""
    extension: str = ""
    media_type: str = ""
    size: int = 0
    hashes: dict[str, str] = field(default_factory=dict)
    object_id: str = ""
    file_id: str = ""
    media_id: str = ""
    primary_file_id: str = ""
    sidecar_role: str = ""
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    license_profile: str = "unknown"
    media_classification: str = ""
    export_allowed: bool = False
    verification_status: str = "unverified"
    latest_verification_timestamp: str = ""
    provenance_summary: str = ""
    searchable_text: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = 1
    builder_version: str = "amigalab-catalog-1"
    source_fingerprint: str = ""
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", document_fingerprint(asdict(self)))

    def as_dict(self):
        return asdict(self)
