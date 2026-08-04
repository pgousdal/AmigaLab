"""Small, testable services used by transaction recovery.

The services deliberately know nothing about plans or selection rules.  They
operate only on an already approved entry and keep temporary files separate
from preserved trees.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5, sha1, sha256, sha512
from pathlib import Path
import os
import shutil

from .models import Hashes, TransactionEntry


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> tuple[Hashes, int]:
    digests = (md5(), sha1(), sha256(), sha512())
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            size += len(chunk)
            for digest in digests:
                digest.update(chunk)
    return Hashes(*(digest.hexdigest() for digest in digests)), size


def contained(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class StagingValidation:
    status: str
    hashes: Hashes | None = None
    size: int = 0
    reason: str = ""


def validate_staging(entry: TransactionEntry, staging_root: Path) -> StagingValidation:
    path = Path(entry.staging_path)
    if not contained(path, staging_root):
        return StagingValidation("unsafe", reason="staging path escapes transaction root")
    if path.name.endswith(".partial") or path.name.endswith(".tmp"):
        return StagingValidation("partial", reason="temporary staging file")
    if not path.exists():
        return StagingValidation("missing", reason="staging file is absent")
    if not path.is_file():
        return StagingValidation("unsafe", reason="staging path is not a regular file")
    hashes, size = hash_file(path)
    expected_size = _size_from_entry(entry)
    if expected_size and size != expected_size:
        return StagingValidation("size-mismatch", hashes, size, "staged size differs from expected")
    if entry.observed_hashes and hashes != entry.observed_hashes:
        return StagingValidation("hash-mismatch", hashes, size, "staged hashes differ from recorded hashes")
    return StagingValidation("valid", hashes, size)


def _size_from_entry(entry: TransactionEntry) -> int:
    # TransactionEntry predates an explicit expected_size field.  A zero-size
    # hash record is still valid; callers that know a size validate it before
    # invoking this service.
    return getattr(entry, "expected_size", 0) or 0


def atomic_copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.amigalab-{os.getpid()}.partial")
    shutil.copyfile(source, temporary)
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    temporary.replace(destination)
    return destination


def verify_destination(path: Path, root: Path, expected: Hashes | None = None) -> StagingValidation:
    if not contained(path, root):
        return StagingValidation("unsafe", reason="destination escapes collection root")
    if not path.is_file():
        return StagingValidation("missing", reason="destination is absent or not a regular file")
    hashes, size = hash_file(path)
    if expected and hashes != expected:
        return StagingValidation("hash-mismatch", hashes, size, "destination hash mismatch")
    return StagingValidation("valid", hashes, size)
