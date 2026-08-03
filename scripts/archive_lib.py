"""Deterministic, non-destructive metadata for archive collections.

Collection data is treated as immutable historical input. This module writes
AmigaLab controls only to a separate metadata directory; every original nested
path, filename, and accompanying file (including Aminet ``.readme`` files) is
retained verbatim and represented in the manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable


MANIFEST_SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_INVALID = 1
EXIT_MISSING = 2
EXIT_CHANGED = 4
EXIT_EXTRA = 8
EXIT_CHECKSUM = 16


class ArchiveError(ValueError):
    """Raised when an archive collection cannot be processed safely."""


@dataclass(frozen=True, order=True)
class ManifestEntry:
    path: str
    size: int
    sha256: str
    modified_time_ns: int


@dataclass(frozen=True)
class VerificationResult:
    missing: tuple[str, ...]
    changed: tuple[str, ...]
    extra: tuple[str, ...]
    checksum_mismatches: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        code = EXIT_OK
        if self.missing:
            code |= EXIT_MISSING
        if self.changed:
            code |= EXIT_CHANGED
        if self.extra:
            code |= EXIT_EXTRA
        if self.checksum_mismatches:
            code |= EXIT_CHECKSUM
        return code

    @property
    def valid(self) -> bool:
        return self.exit_code == EXIT_OK


def _relative_path(collection: Path, path: Path) -> str:
    return path.relative_to(collection).as_posix()


def _data_files(collection: Path) -> Iterable[Path]:
    """Yield every original file without rewriting or reorganizing it."""
    for path in sorted(collection.rglob("*"), key=lambda candidate: candidate.as_posix()):
        if path.is_file():
            yield path


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_entry(collection: Path, path: Path) -> ManifestEntry:
    stat_result = path.stat()
    return ManifestEntry(
        path=_relative_path(collection, path),
        size=stat_result.st_size,
        sha256=file_sha256(path),
        modified_time_ns=stat_result.st_mtime_ns,
    )


def build_collection_manifest(collection: Path, metadata_directory: Path) -> tuple[ManifestEntry, ...]:
    collection = collection.resolve()
    if not collection.is_dir():
        raise ArchiveError(f"Collection directory does not exist: {collection}")
    entries = tuple(sorted((manifest_entry(collection, path) for path in _data_files(collection))))
    metadata_directory.mkdir(parents=True, exist_ok=True)
    payload = {"files": [asdict(entry) for entry in entries], "schema_version": MANIFEST_SCHEMA_VERSION}
    (metadata_directory / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (metadata_directory / "checksums.sha256").write_text(
        "".join(f"{entry.sha256}  {entry.path}\n" for entry in entries), encoding="utf-8"
    )
    return entries


def load_manifest(metadata_directory: Path) -> tuple[ManifestEntry, ...]:
    manifest_path = metadata_directory / "manifest.json"
    if not manifest_path.is_file():
        raise ArchiveError(f"Manifest file is missing: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload["schema_version"] != MANIFEST_SCHEMA_VERSION:
            raise ArchiveError(f"Unsupported manifest schema: {payload['schema_version']}")
        entries = tuple(ManifestEntry(**entry) for entry in payload["files"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ArchiveError(f"Invalid manifest file: {manifest_path}") from error
    if tuple(sorted(entries)) != entries:
        raise ArchiveError(f"Manifest entries are not deterministically ordered: {manifest_path}")
    return entries


def load_checksums(metadata_directory: Path) -> dict[str, str]:
    checksum_path = metadata_directory / "checksums.sha256"
    if not checksum_path.is_file():
        raise ArchiveError(f"Checksum file is missing: {checksum_path}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            digest, path = line.split("  ", maxsplit=1)
        except ValueError as error:
            raise ArchiveError(f"Invalid checksum entry at {checksum_path}:{line_number}") from error
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ArchiveError(f"Invalid SHA-256 at {checksum_path}:{line_number}")
        if not path or path in entries:
            raise ArchiveError(f"Invalid checksum path at {checksum_path}:{line_number}")
        entries[path] = digest
    return entries


def verify_collection(collection: Path, metadata_directory: Path) -> VerificationResult:
    collection = collection.resolve()
    if not collection.is_dir():
        raise ArchiveError(f"Collection directory does not exist: {collection}")
    expected_entries = load_manifest(metadata_directory)
    checksum_entries = load_checksums(metadata_directory)
    expected_by_path = {entry.path: entry for entry in expected_entries}
    actual_by_path = {_relative_path(collection, path): path for path in _data_files(collection)}

    missing = tuple(sorted(set(expected_by_path) - set(actual_by_path)))
    extra = tuple(sorted(set(actual_by_path) - set(expected_by_path)))
    changed = tuple(
        path
        for path in sorted(set(expected_by_path) & set(actual_by_path))
        if manifest_entry(collection, actual_by_path[path]).sha256 != expected_by_path[path].sha256
    )
    expected_checksums = {entry.path: entry.sha256 for entry in expected_entries}
    checksum_mismatches = tuple(
        sorted(
            path
            for path in set(expected_checksums) | set(checksum_entries)
            if checksum_entries.get(path) != expected_checksums.get(path)
        )
    )
    return VerificationResult(missing, changed, extra, checksum_mismatches)
