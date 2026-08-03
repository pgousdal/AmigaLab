"""Read-only adapters for directories and archive media."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tarfile
from typing import BinaryIO, Iterator
import zipfile


@dataclass(frozen=True)
class SourceEntry:
    path: str
    size: int
    modified_time: float | None
    is_file: bool = True
    unsupported_reason: str | None = None


def _safe_path(name: str) -> str:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe source path: {name}")
    return path.as_posix()


class DirectoryAdapter:
    def __init__(self, root: Path):
        if not root.is_dir():
            raise ValueError(f"directory source does not exist: {root}")
        self.root = root

    def entries(self) -> Iterator[SourceEntry]:
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                stat = path.stat()
                yield SourceEntry(path.relative_to(self.root).as_posix(), stat.st_size, stat.st_mtime)

    def open(self, entry: SourceEntry) -> BinaryIO:
        return (self.root / entry.path).open("rb")

    def close(self) -> None:
        return None


class ZipAdapter:
    def __init__(self, archive: Path):
        self.archive = archive
        self.handle = zipfile.ZipFile(archive, "r")

    def entries(self) -> Iterator[SourceEntry]:
        for info in sorted(self.handle.infolist(), key=lambda item: item.filename):
            try:
                path = _safe_path(info.filename)
            except ValueError as error:
                yield SourceEntry(info.filename, info.file_size, None, False, str(error))
                continue
            is_file = not info.is_dir() and not info.filename.endswith("/")
            yield SourceEntry(path, info.file_size, None, is_file)

    def open(self, entry: SourceEntry) -> BinaryIO:
        if entry.unsupported_reason or not entry.is_file:
            raise ValueError(entry.unsupported_reason or f"not a file: {entry.path}")
        return self.handle.open(entry.path, "r")

    def close(self) -> None:
        self.handle.close()


class TarAdapter:
    def __init__(self, archive: Path):
        self.handle = tarfile.open(archive, "r:*")

    def entries(self) -> Iterator[SourceEntry]:
        for info in sorted(self.handle.getmembers(), key=lambda item: item.name):
            try:
                path = _safe_path(info.name)
            except ValueError as error:
                yield SourceEntry(info.name, info.size, info.mtime, False, str(error))
                continue
            if info.isfile():
                yield SourceEntry(path, info.size, info.mtime)
            elif not info.isdir():
                yield SourceEntry(path, info.size, info.mtime, False, "unsupported special or link entry")

    def open(self, entry: SourceEntry) -> BinaryIO:
        if entry.unsupported_reason:
            raise ValueError(entry.unsupported_reason)
        member = self.handle.extractfile(entry.path)
        if member is None:
            raise ValueError(f"unable to open archive member: {entry.path}")
        return member

    def close(self) -> None:
        self.handle.close()


class IsoAdapter:
    """Optional userspace ISO reader; no loop mount or source mutation."""

    def __init__(self, image: Path):
        try:
            import pycdlib  # type: ignore
        except ImportError as error:
            raise RuntimeError("ISO support requires optional pycdlib; install it to inspect ISO images") from error
        self.handle = pycdlib.PyCdlib()
        self.handle.open(str(image))

    def entries(self) -> Iterator[SourceEntry]:
        # pycdlib's walk is read-only and returns ISO names; callers retain them as source paths.
        for root, _directories, files in self.handle.walk(iso_path="/"):
            for name in files:
                path = f"{root.rstrip('/')}/{name}".lstrip("/")
                yield SourceEntry(path, 0, None)

    def open(self, entry: SourceEntry) -> BinaryIO:
        buffer = BytesIO()
        self.handle.get_file_from_iso_fp(buffer, iso_path="/" + entry.path)
        buffer.seek(0)
        return buffer

    def close(self) -> None:
        self.handle.close()


def adapter_for(path: Path, kind: str | None = None):
    kind = kind or ("directory" if path.is_dir() else path.suffix.lower().lstrip("."))
    if kind in {"directory", "mounted"}:
        return DirectoryAdapter(path)
    if kind == "zip":
        return ZipAdapter(path)
    if kind in {"tar", "tgz", "gz", "bz2", "xz", "tar.gz", "tar.bz2", "tar.xz"}:
        return TarAdapter(path)
    if kind in {"iso", "iso9660"}:
        return IsoAdapter(path)
    if kind in {"lha", "lzh"}:
        raise RuntimeError("LHA support is optional and unavailable: install a suitable LHA reader")
    raise ValueError(f"unsupported source adapter: {kind}")
