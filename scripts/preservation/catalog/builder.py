from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json

from ..storage import MetadataStore
from ..external.storage import stable_id
from .models import CatalogDocument
from .readme import decode_readme


def _read_json_dir(path: Path):
    if not path.is_dir(): return ()
    values = []
    for item in sorted(path.glob("*.json")):
        try: values.append(json.loads(item.read_text(encoding="utf-8")))
        except (OSError, ValueError): continue
    return tuple(values)


def build_documents(metadata_root: Path, archive_root: Path, max_text_bytes: int = 1_048_576) -> tuple[CatalogDocument, ...]:
    store = MetadataStore(metadata_root); documents = []
    sources = {str(v.get("id")): v for v in _read_json_dir(metadata_root / "sources")}
    for obj in store.list_objects():
        files = list(obj.files)
        primary = files[0] if files else None
        object_text = " ".join(f.original_relative_path for f in files)
        documents.append(CatalogDocument("object:" + obj.id, "object", obj.id, obj.original_collection,
            title=primary.original_filename if primary else obj.original_relative_path,
            display_name=obj.original_relative_path, relative_path=obj.original_relative_path,
            parent_path=str(Path(obj.original_relative_path).parent), object_id=obj.id,
            source_ids=obj.provenance_source_ids, verification_status="verified" if obj.verification_event_ids else "unverified",
            searchable_text=object_text, keywords=tuple(sorted({Path(f.original_filename).suffix.lower().lstrip('.') for f in files}))))
        for index, file in enumerate(files):
            file_id = stable_id({"object_id": obj.id, "path": file.original_relative_path})
            path = archive_root / obj.original_collection / file.original_relative_path
            readme_text = ""
            if path.suffix.lower() == ".readme" and path.is_file():
                parsed = decode_readme(path, max_text_bytes); readme_text = parsed.raw_text
            status = "verified" if obj.verification_event_ids else "unverified"
            doc = CatalogDocument("file:" + file_id, "file", file_id, obj.original_collection,
                title=file.original_filename, display_name=file.original_filename,
                historical_filename=file.original_filename, relative_path=file.original_relative_path,
                parent_path=str(Path(file.original_relative_path).parent), extension=Path(file.original_filename).suffix.lower().lstrip('.'),
                size=file.size, hashes=asdict(file.hashes), object_id=obj.id, file_id=file_id,
                sidecar_role="sidecar" if Path(file.original_filename).suffix.lower() in {".readme", ".info", ".txt", ".nfo", ".diz"} else "primary",
                source_ids=obj.provenance_source_ids, verification_status=status,
                searchable_text=" ".join((file.original_filename, file.original_relative_path, readme_text)))
            documents.append(doc)
            if path.suffix.lower() == ".readme":
                documents.append(CatalogDocument("readme:" + file_id, "readme", file_id, obj.original_collection,
                    title=file.original_filename, display_name=file.original_filename, historical_filename=file.original_filename,
                    relative_path=file.original_relative_path, parent_path=str(Path(file.original_relative_path).parent),
                    extension="readme", size=file.size, hashes=asdict(file.hashes), object_id=obj.id, file_id=file_id,
                    primary_file_id=stable_id({"object_id": obj.id, "path": files[0].original_relative_path}) if index else "",
                    sidecar_role="readme", source_ids=obj.provenance_source_ids, verification_status=status,
                    searchable_text=" ".join((file.original_filename, file.original_relative_path, readme_text))))
    for media in _read_json_dir(metadata_root / "media"):
        hashes = media.get("hashes", {})
        documents.append(CatalogDocument("media:" + str(media.get("id")), "media", str(media.get("id")),
            title=str(media.get("title", "")), display_name=str(media.get("original_filename", "")),
            historical_filename=str(media.get("original_filename", "")), size=int(media.get("size", 0) or 0), hashes=hashes,
            media_id=str(media.get("id")), source_ids=(str(media.get("source_id")),) if media.get("source_id") else (),
            license_profile=str(media.get("license_profile", "unknown")), media_classification=str(media.get("media_classification", "")),
            export_allowed=bool(media.get("export_allowed", False)), searchable_text=" ".join(str(media.get(k, "")) for k in ("title", "original_filename", "edition", "publisher"))))
    for source in sources.values():
        documents.append(CatalogDocument("source:" + str(source.get("id")), "source", str(source.get("id")),
            title=str(source.get("name", source.get("id", ""))), display_name=str(source.get("id", "")),
            license_profile=str(source.get("license_profile", "unknown")), media_classification=str(source.get("media_classification", "")),
            searchable_text=" ".join(str(source.get(k, "")) for k in ("id", "name", "kind", "locator", "notes"))))
    for report in _read_json_dir(metadata_root / "verification-reports"):
        report_id = str(report.get("id", ""))
        if report_id:
            documents.append(CatalogDocument("verification-report:" + report_id, "verification-report", report_id,
                collection=str(report.get("collection", "")), title=f"verification {report.get('collection', '')}",
                verification_status=str(report.get("result", "")), searchable_text=json.dumps(report, sort_keys=True)))
    return tuple(sorted(documents, key=lambda d: d.id))
