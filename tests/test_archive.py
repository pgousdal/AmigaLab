from __future__ import annotations

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.archive_lib import (
    EXIT_CHANGED,
    EXIT_CHECKSUM,
    EXIT_EXTRA,
    EXIT_MISSING,
    build_collection_manifest,
    verify_collection,
)


def metadata_directory(tmp_path: Path) -> Path:
    return tmp_path.parent / "metadata" / "collections" / tmp_path.name


def test_empty_collection_has_stable_separate_control_files(tmp_path: Path) -> None:
    metadata = metadata_directory(tmp_path)
    entries = build_collection_manifest(tmp_path, metadata)

    assert entries == ()
    assert not (tmp_path / "manifest.json").exists()
    assert json.loads((metadata / "manifest.json").read_text()) == {"files": [], "schema_version": 1}
    assert (metadata / "checksums.sha256").read_text() == ""
    assert verify_collection(tmp_path, metadata).valid


def test_manifest_includes_nested_files_in_deterministic_order(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "second.bin").write_bytes(b"second")
    (tmp_path / "first.bin").write_bytes(b"first")

    entries = build_collection_manifest(tmp_path, metadata_directory(tmp_path))

    assert [entry.path for entry in entries] == ["first.bin", "nested/second.bin"]
    assert all(entry.size > 0 for entry in entries)
    assert all(len(entry.sha256) == 64 for entry in entries)


def test_manifest_preserves_historical_paths_and_accompanying_readmes(tmp_path: Path) -> None:
    original_directory = tmp_path / "dev" / "gcc"
    original_directory.mkdir(parents=True)
    archive = original_directory / "tool.lha"
    readme = original_directory / "tool.readme"
    archive.write_bytes(b"original archive")
    readme.write_text("original Aminet description\n", encoding="utf-8")
    original_readme = readme.read_bytes()

    entries = build_collection_manifest(tmp_path, metadata_directory(tmp_path))

    assert [entry.path for entry in entries] == ["dev/gcc/tool.lha", "dev/gcc/tool.readme"]
    assert archive.read_bytes() == b"original archive"
    assert readme.read_bytes() == original_readme


def test_rebuilding_an_unchanged_collection_is_byte_stable(tmp_path: Path) -> None:
    (tmp_path / "asset.adf").write_bytes(b"archive data")
    metadata = metadata_directory(tmp_path)
    build_collection_manifest(tmp_path, metadata)
    first_manifest = (metadata / "manifest.json").read_bytes()
    first_checksums = (metadata / "checksums.sha256").read_bytes()

    build_collection_manifest(tmp_path, metadata)

    assert (metadata / "manifest.json").read_bytes() == first_manifest
    assert (metadata / "checksums.sha256").read_bytes() == first_checksums


def test_verification_reports_missing_changed_and_extra_files(tmp_path: Path) -> None:
    (tmp_path / "changed.bin").write_bytes(b"before")
    (tmp_path / "missing.bin").write_bytes(b"missing")
    metadata = metadata_directory(tmp_path)
    build_collection_manifest(tmp_path, metadata)
    (tmp_path / "changed.bin").write_bytes(b"after")
    (tmp_path / "missing.bin").unlink()
    (tmp_path / "extra.bin").write_bytes(b"extra")

    result = verify_collection(tmp_path, metadata)

    assert result.missing == ("missing.bin",)
    assert result.changed == ("changed.bin",)
    assert result.extra == ("extra.bin",)
    assert result.checksum_mismatches == ()
    assert result.exit_code == EXIT_MISSING | EXIT_CHANGED | EXIT_EXTRA


def test_verification_reports_checksum_file_mismatch(tmp_path: Path) -> None:
    (tmp_path / "asset.bin").write_bytes(b"asset")
    metadata = metadata_directory(tmp_path)
    build_collection_manifest(tmp_path, metadata)
    (metadata / "checksums.sha256").write_text("0" * 64 + "  asset.bin\n")

    result = verify_collection(tmp_path, metadata)

    assert result.checksum_mismatches == ("asset.bin",)
    assert result.exit_code == EXIT_CHECKSUM
