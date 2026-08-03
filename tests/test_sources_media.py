from __future__ import annotations

from pathlib import Path
import tarfile
import zipfile

import pytest

from scripts.preservation.media import discover_candidates, register_media
from scripts.preservation.policy import export_allowed, validate_license_profile
from scripts.preservation.sources import DirectoryAdapter, TarAdapter, ZipAdapter


def test_directory_zip_and_tar_adapters_preserve_nested_paths(tmp_path: Path) -> None:
    root = tmp_path / "directory"
    (root / "nested").mkdir(parents=True)
    (root / "nested/file.readme").write_text("readme")
    assert [entry.path for entry in DirectoryAdapter(root).entries()] == ["nested/file.readme"]
    zip_path = tmp_path / "source.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("nested/file.readme", "readme")
    zip_adapter = ZipAdapter(zip_path)
    assert [entry.path for entry in zip_adapter.entries()] == ["nested/file.readme"]
    zip_adapter.close()
    tar_path = tmp_path / "source.tar"
    with tarfile.open(tar_path, "w") as archive:
        archive.add(root / "nested/file.readme", arcname="nested/file.readme")
    tar_adapter = TarAdapter(tar_path)
    assert [entry.path for entry in tar_adapter.entries()] == ["nested/file.readme"]
    tar_adapter.close()


def test_archive_adapter_rejects_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../escape", "bad")
    entry = next(iter(ZipAdapter(zip_path).entries()))
    assert entry.unsupported_reason


def test_media_hashes_license_policy_and_conservative_discovery(tmp_path: Path) -> None:
    media = tmp_path / "synthetic.iso"
    media.write_bytes(b"media")
    (tmp_path / "kickstart.rom").write_bytes(b"rom")
    record = register_media(media, "local", "Synthetic media", "local-only")
    assert len(record.hashes.sha256) == 64
    assert not record.redistributable
    assert not export_allowed("commercial")
    assert export_allowed("redistributable", explicit=True)
    assert "bad" not in validate_license_profile("unknown")
    assert discover_candidates(tmp_path)[0]["kind"] == "rom"
