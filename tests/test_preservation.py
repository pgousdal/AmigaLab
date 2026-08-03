from __future__ import annotations

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preservation.manifest import append_provenance, create_object, stable_object_id
from scripts.preservation.models import Source
from scripts.preservation.storage import MetadataStore
from scripts.preservation.verification import append_verification, verify_object


def source() -> Source:
    return Source("aminet-live", "Aminet Live", "ftp mirror", "https://aminet.net")


def test_object_creation_has_stable_original_path_and_id(tmp_path: Path) -> None:
    path = tmp_path / "util" / "arc"
    path.mkdir(parents=True)
    (path / "lha.run").write_bytes(b"lha")
    object_, _ = create_object("aminet", tmp_path, "util/arc/lha.run", source())
    assert object_.id == "aminet:util/arc/lha.run"
    assert stable_object_id("aminet", "util/arc/lha.run") == object_.id
    assert object_.files[0].original_relative_path == "util/arc/lha.run"


def test_object_associates_multiple_sidecar_files(tmp_path: Path) -> None:
    (tmp_path / "DiskMaster2.lha").write_bytes(b"archive")
    (tmp_path / "DiskMaster2.readme").write_text("readme")
    (tmp_path / "DiskMaster2.info").write_bytes(b"info")
    (tmp_path / "Other.txt").write_text("other")
    object_, _ = create_object("aminet", tmp_path, "DiskMaster2.lha", source())
    assert [file.original_filename for file in object_.files] == ["DiskMaster2.lha", "DiskMaster2.info", "DiskMaster2.readme"]


def test_file_hashes_include_all_required_algorithms(tmp_path: Path) -> None:
    (tmp_path / "Workbench31.adf").write_bytes(b"disk image")
    object_, _ = create_object("adf", tmp_path, "Workbench31.adf", source())
    hashes = object_.files[0].hashes
    assert (len(hashes.md5), len(hashes.sha1), len(hashes.sha256), len(hashes.sha512)) == (32, 40, 64, 128)


def test_multiple_provenance_records_are_preserved(tmp_path: Path) -> None:
    (tmp_path / "tool.lha").write_bytes(b"tool")
    first, first_event = create_object("aminet", tmp_path, "tool.lha", source())
    personal = Source("personal", "Personal Collection", "personal", "shelf A")
    second, second_event = create_object("aminet", tmp_path, "tool.lha", personal)
    object_ = append_provenance(first, personal, second_event)
    assert object_.provenance_source_ids == ("aminet-live", "personal")
    assert object_.import_event_ids == (first_event.id, second_event.id)


def test_metadata_serialization_is_separate_from_collection(tmp_path: Path) -> None:
    collection = tmp_path / "aminet"
    collection.mkdir()
    (collection / "tool.lha").write_bytes(b"tool")
    object_, event = create_object("aminet", collection, "tool.lha", source())
    metadata = tmp_path / "metadata"
    store = MetadataStore(metadata)
    object_path = store.save_object(object_)
    import_path = store.save_import(event)
    assert object_path.is_relative_to(metadata)
    assert import_path.is_relative_to(metadata)
    assert sorted(path.name for path in collection.iterdir()) == ["tool.lha"]
    assert json.loads(object_path.read_text())["id"] == object_.id


def test_verification_history_records_success_and_failure(tmp_path: Path) -> None:
    (tmp_path / "FishDisk001.adf").write_bytes(b"disk")
    object_, _ = create_object("fish", tmp_path, "FishDisk001.adf", source())
    successful = verify_object(object_, tmp_path)
    object_ = append_verification(object_, successful)
    (tmp_path / "FishDisk001.adf").write_bytes(b"changed")
    failed = verify_object(object_, tmp_path)
    assert successful.success and successful.failure_reason is None
    assert object_.verification_event_ids == (successful.id,)
    assert not failed.success
    assert "hash mismatch" in (failed.failure_reason or "")
