"""Read-only scans and copy-only imports for preservation collections."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shutil

from .manifest import SIDECAR_SUFFIXES, append_provenance, create_object
from .models import PreservationObject, Source
from .storage import MetadataStore


SUPPORTED_SOURCE_KINDS = frozenset({"directory", "iso", "archive", "mounted"})


@dataclass(frozen=True)
class ScanPreview:
    new_objects: int
    existing_objects: int
    changed: int
    conflicts: int
    relative_paths: tuple[str, ...]


def _primary_paths(location: Path) -> tuple[str, ...]:
    files = [path for path in location.rglob("*") if path.is_file()]
    paths = {path.relative_to(location).as_posix() for path in files}
    primary: list[str] = []
    for path in sorted(paths):
        candidate = Path(path)
        base = candidate.name.rsplit(".", maxsplit=1)[0]
        has_primary = any(
            sibling != path
            and Path(sibling).parent == candidate.parent
            and Path(sibling).name.rsplit(".", maxsplit=1)[0] == base
            and Path(sibling).suffix.lower() not in SIDECAR_SUFFIXES
            for sibling in paths
        )
        if candidate.suffix.lower() not in SIDECAR_SUFFIXES or not has_primary:
            primary.append(path)
    return tuple(primary)


def _primary_sha256(object_: PreservationObject) -> str:
    return object_.files[0].hashes.sha256


def scan(location: Path, collection: str, store: MetadataStore, archive_root: Path) -> ScanPreview:
    if not location.is_dir():
        raise ValueError(f"Only directory or mounted filesystem scans are implemented: {location}")
    existing = {object_.id: object_ for object_ in store.list_objects()}
    known_hashes = {_primary_sha256(object_) for object_ in existing.values() if object_.files}
    new_objects = existing_objects = changed = conflicts = 0
    relative_paths = _primary_paths(location)
    from .manifest import preserved_file, stable_object_id

    for relative_path in relative_paths:
        object_id = stable_object_id(collection, relative_path)
        digest = preserved_file(collection, location, relative_path).hashes.sha256
        destination = archive_root / collection / relative_path
        if object_id in existing:
            if _primary_sha256(existing[object_id]) == digest:
                existing_objects += 1
            else:
                changed += 1
        elif digest in known_hashes:
            existing_objects += 1
        elif destination.exists():
            conflicts += 1
        else:
            new_objects += 1
    return ScanPreview(new_objects, existing_objects, changed, conflicts, relative_paths)


def import_source(
    location: Path,
    collection: str,
    source: Source,
    store: MetadataStore,
    archive_root: Path,
    staging_root: Path,
    confirmed: bool,
) -> ScanPreview:
    if not confirmed:
        raise PermissionError("Import requires explicit confirmation: pass --yes")
    preview = scan(location, collection, store, archive_root)
    existing = {object_.id: object_ for object_ in store.list_objects()}
    hash_index = {_primary_sha256(object_): object_ for object_ in existing.values() if object_.files}
    stage = staging_root / source.id
    for relative_path in preview.relative_paths:
        object_id = f"{collection}:{relative_path}"
        candidate, event = create_object(collection, location, relative_path, source)
        duplicate = existing.get(object_id) or hash_index.get(_primary_sha256(candidate))
        if duplicate is not None:
            store.save_import(event)
            store.save_object(append_provenance(duplicate, source, event))
            continue
        destination_root = archive_root / collection
        conflict = any((destination_root / file.original_relative_path).exists() for file in candidate.files)
        if conflict:
            continue
        for file in candidate.files:
            source_path = location / file.original_relative_path
            staged_path = stage / file.original_relative_path
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, staged_path)
        staged_event = replace(event, result="staged")
        store.save_import(staged_event)
        store.save_object(candidate)
        try:
            for file in candidate.files:
                staged_path = stage / file.original_relative_path
                target_path = destination_root / file.original_relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_path, target_path)
        except OSError:
            store.save_import(replace(event, result="failed"))
            continue
        store.save_import(event)
        existing[candidate.id] = candidate
        hash_index[_primary_sha256(candidate)] = candidate
    return preview
