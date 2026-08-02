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


def test_empty_collection_has_stable_control_files(tmp_path: Path) -> None:
    entries = build_collection_manifest(tmp_path)

    assert entries == ()
    assert json.loads((tmp_path / "manifest.json").read_text()) == {"files": [], "schema_version": 1}
    assert (tmp_path / "checksums.sha256").read_text() == ""
    assert verify_collection(tmp_path).valid


def test_manifest_includes_nested_files_in_deterministic_order(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "second.bin").write_bytes(b"second")
    (tmp_path / "first.bin").write_bytes(b"first")

    entries = build_collection_manifest(tmp_path)

    assert [entry.path for entry in entries] == ["first.bin", "nested/second.bin"]
    assert all(entry.size > 0 for entry in entries)
    assert all(len(entry.sha256) == 64 for entry in entries)


def test_rebuilding_an_unchanged_collection_is_byte_stable(tmp_path: Path) -> None:
    (tmp_path / "asset.adf").write_bytes(b"archive data")
    build_collection_manifest(tmp_path)
    first_manifest = (tmp_path / "manifest.json").read_bytes()
    first_checksums = (tmp_path / "checksums.sha256").read_bytes()

    build_collection_manifest(tmp_path)

    assert (tmp_path / "manifest.json").read_bytes() == first_manifest
    assert (tmp_path / "checksums.sha256").read_bytes() == first_checksums


def test_verification_reports_missing_changed_and_extra_files(tmp_path: Path) -> None:
    (tmp_path / "changed.bin").write_bytes(b"before")
    (tmp_path / "missing.bin").write_bytes(b"missing")
    build_collection_manifest(tmp_path)
    (tmp_path / "changed.bin").write_bytes(b"after")
    (tmp_path / "missing.bin").unlink()
    (tmp_path / "extra.bin").write_bytes(b"extra")

    result = verify_collection(tmp_path)

    assert result.missing == ("missing.bin",)
    assert result.changed == ("changed.bin",)
    assert result.extra == ("extra.bin",)
    assert result.checksum_mismatches == ()
    assert result.exit_code == EXIT_MISSING | EXIT_CHANGED | EXIT_EXTRA


def test_verification_reports_checksum_file_mismatch(tmp_path: Path) -> None:
    (tmp_path / "asset.bin").write_bytes(b"asset")
    build_collection_manifest(tmp_path)
    (tmp_path / "checksums.sha256").write_text("0" * 64 + "  asset.bin\n")

    result = verify_collection(tmp_path)

    assert result.checksum_mismatches == ("asset.bin",)
    assert result.exit_code == EXIT_CHECKSUM
