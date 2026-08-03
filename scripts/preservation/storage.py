"""Serialize separate preservation metadata without touching collections."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from .models import Hashes, ImportEvent, PreservedFile, PreservationObject, Source, VerificationEvent


class MetadataStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure_layout(self) -> None:
        for directory in ("collections", "objects", "sources", "imports", "verification"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def _write(self, category: str, identifier: str, value: object) -> Path:
        self.ensure_layout()
        path = self.root / category / f"{sha256(identifier.encode()).hexdigest()}.json"
        path.write_text(json.dumps(asdict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _read_json(self, category: str) -> list[dict[str, object]]:
        directory = self.root / category
        if not directory.is_dir():
            return []
        return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]

    def save_source(self, source: Source) -> Path:
        return self._write("sources", source.id, source)

    def save_object(self, object_: PreservationObject) -> Path:
        return self._write("objects", object_.id, object_)

    def save_import(self, event: ImportEvent) -> Path:
        return self._write("imports", event.id, event)

    def save_verification(self, event: VerificationEvent) -> Path:
        return self._write("verification", event.id, event)

    def get_source(self, source_id: str) -> Source | None:
        for item in self._read_json("sources"):
            if item["id"] == source_id:
                return Source(**item)
        return None

    def list_objects(self) -> tuple[PreservationObject, ...]:
        objects: list[PreservationObject] = []
        for item in self._read_json("objects"):
            files = tuple(
                PreservedFile(
                    hashes=Hashes(**file_item.pop("hashes")),
                    **file_item,
                )
                for raw_file in item.pop("files")
                for file_item in [dict(raw_file)]
            )
            objects.append(
                PreservationObject(
                    files=files,
                    provenance_source_ids=tuple(item.get("provenance_source_ids", [])),
                    import_event_ids=tuple(item.get("import_event_ids", [])),
                    verification_event_ids=tuple(item.get("verification_event_ids", [])),
                    id=str(item["id"]),
                    original_collection=str(item["original_collection"]),
                    original_relative_path=str(item["original_relative_path"]),
                )
            )
        return tuple(objects)
