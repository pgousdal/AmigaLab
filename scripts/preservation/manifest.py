"""Build preservation objects from immutable collection files."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import md5, sha1, sha256, sha512
from pathlib import Path
from uuid import uuid4

from .models import Hashes, ImportEvent, PreservedFile, PreservationObject, Source


SIDECAR_SUFFIXES = frozenset({".readme", ".info", ".txt", ".nfo", ".diz"})
TOOL_VERSION = "amigalab-m2.1"


def stable_object_id(collection: str, original_relative_path: str) -> str:
    path = Path(original_relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Object path must be a safe relative path: {original_relative_path}")
    return f"{collection}:{path.as_posix()}"


def _all_hashes(path: Path) -> Hashes:
    digests = (md5(), sha1(), sha256(), sha512())
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            for digest in digests:
                digest.update(chunk)
    return Hashes(*(digest.hexdigest() for digest in digests))


def preserved_file(collection: str, collection_root: Path, relative_path: str) -> PreservedFile:
    path = collection_root / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Preserved file does not exist: {path}")
    stat_result = path.stat()
    return PreservedFile(collection, Path(relative_path).as_posix(), path.name, stat_result.st_size, stat_result.st_mtime_ns, _all_hashes(path))


def discover_sidecars(collection_root: Path, primary_relative_path: str) -> tuple[str, ...]:
    primary = Path(primary_relative_path)
    base_name = primary.name.rsplit(".", maxsplit=1)[0]
    sidecars = [
        candidate.relative_to(collection_root).as_posix()
        for candidate in (collection_root / primary.parent).iterdir()
        if candidate.is_file()
        and candidate.name.rsplit(".", maxsplit=1)[0] == base_name
        and candidate.suffix.lower() in SIDECAR_SUFFIXES
    ]
    return tuple(sorted(sidecars))


def create_object(collection: str, collection_root: Path, primary_relative_path: str, source: Source) -> tuple[PreservationObject, ImportEvent]:
    object_id = stable_object_id(collection, primary_relative_path)
    file_paths = (Path(primary_relative_path).as_posix(),) + discover_sidecars(collection_root, primary_relative_path)
    files = tuple(preserved_file(collection, collection_root, path) for path in file_paths)
    event = ImportEvent(str(uuid4()), datetime.now(timezone.utc).isoformat(), source.id, "metadata import", TOOL_VERSION, "success")
    return PreservationObject(object_id, collection, Path(primary_relative_path).as_posix(), files, (source.id,), (event.id,)), event


def append_provenance(object_: PreservationObject, source: Source, event: ImportEvent) -> PreservationObject:
    """Return a new object with additive provenance; existing history is retained."""
    sources = tuple(dict.fromkeys(object_.provenance_source_ids + (source.id,)))
    events = tuple(dict.fromkeys(object_.import_event_ids + (event.id,)))
    return replace(object_, provenance_source_ids=sources, import_event_ids=events)
