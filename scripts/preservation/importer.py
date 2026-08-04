"""Read-only scans and copy-only imports for preservation collections."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shutil
from hashlib import sha256

from .manifest import SIDECAR_SUFFIXES, append_provenance, create_object
from .models import PreservationObject, Source
from .storage import MetadataStore
from .models import TransactionEntry
from .transactions import TransactionStore


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


def import_selected(location: Path, collection: str, source: Source, selected: tuple[str, ...], store: MetadataStore, archive_root: Path, staging_root: Path, transaction_id: str | None = None) -> tuple[int, int]:
    """Copy exactly the approved entry set; no selection rules are reevaluated."""
    stage = staging_root / source.id / "approved"
    destination_root = archive_root / collection
    copied = reused = 0
    transaction_id = transaction_id or f"selected-{source.id}"
    transaction_store = TransactionStore(store.root)
    adapter = None if location.is_dir() else __import__("preservation.sources", fromlist=["adapter_for"]).adapter_for(location, source.kind)
    try:
      for relative_path in selected:
        entry = TransactionEntry(
            id=sha256(f"{transaction_id}:import-member:{source.id}:{relative_path}:{collection}/{relative_path}".encode()).hexdigest(),
            transaction_id=transaction_id, source_path=relative_path, target_path=str(destination_root / relative_path),
            staging_path=str(stage / relative_path), state="pending")
        transaction_store.save_entry(entry)
        entry = transaction_store.transition(entry, "opening-source", "opening-source", "import-member")
        source_root = location
        if adapter is not None:
            entry = next((item for item in adapter.entries() if item.path == relative_path), None)
            if entry is None or entry.unsupported_reason:
                raise ValueError(f"unsupported or missing archive member: {relative_path}")
            staged_source = stage / relative_path
            staged_source.parent.mkdir(parents=True, exist_ok=True)
            with adapter.open(entry) as source_stream, staged_source.open("wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream)
            source_root = stage
            entry = transaction_store.transition(entry, "streaming", "streaming", "stream-member")
            entry = transaction_store.transition(entry, "staging", "staging", "stage-member")
            entry = transaction_store.transition(entry, "staged", "staging", "finalize-stage")
        candidate, event = create_object(collection, source_root, relative_path, source)
        if entry.state == "pending":
            entry = transaction_store.transition(entry, "opening-source", "opening-source", "import-member")
        if entry.state == "opening-source":
            entry = transaction_store.transition(entry, "streaming", "streaming", "stream-member")
            entry = transaction_store.transition(entry, "staging", "staging", "stage-member")
            entry = transaction_store.transition(entry, "staged", "staging", "finalize-stage")
        target = destination_root / relative_path
        if target.exists():
            existing = preserved_file(collection, destination_root, relative_path)
            if existing.hashes.sha256 != candidate.files[0].hashes.sha256:
                raise ValueError(f"blocking destination conflict: {relative_path}")
            store.save_import(event)
            transaction_store.transition(entry, "reused", "verifying", "reuse-identical")
            reused += 1
            continue
        for file in candidate.files:
            staged = stage / file.original_relative_path
            staged.parent.mkdir(parents=True, exist_ok=True)
            if source_root == stage and staged != stage / file.original_relative_path:
                raise ValueError("invalid staged source path")
            if source_root != stage:
                shutil.copy2(location / file.original_relative_path, staged)
            destination = destination_root / file.original_relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.amigalab-partial")
            shutil.copy2(staged, temporary)
            if sha256(temporary.read_bytes()).hexdigest() != file.hashes.sha256:
                temporary.unlink(missing_ok=True)
                raise ValueError(f"destination verification failed: {relative_path}")
            temporary.replace(destination)
        transaction_store.transition(entry, "copying", "copying", "place-destination")
        transaction_store.transition(entry, "verifying", "verifying", "verify-destination")
        store.save_import(event)
        store.save_object(candidate)
        transaction_store.transition(entry, "metadata-writing", "metadata-writing", "write-object")
        transaction_store.transition(entry, "completed", "completed", "complete-entry")
        copied += 1
    finally:
      if adapter is not None:
        adapter.close()
    return copied, reused
