from pathlib import Path

from scripts.preservation.models import Hashes, PreservedFile, PreservationObject
from scripts.preservation.services import hash_file
from scripts.preservation.storage import MetadataStore
from scripts.preservation.verification_reports import verify_collection, reconciliation, repair_plan
from scripts.preservation.traces import object_trace, file_trace


def _fixture(tmp_path: Path):
    root = tmp_path / "aminet"
    (root / "util" / "arc").mkdir(parents=True)
    path = root / "util" / "arc" / "example.lha"
    path.write_bytes(b"synthetic archive")
    hashes, size = hash_file(path)
    obj = PreservationObject(
        "obj-1", "aminet", "util/arc/example.lha",
        (PreservedFile("aminet", "util/arc/example.lha", "example.lha", size, path.stat().st_mtime_ns, hashes),),
        ("source-1",), ("import-1",), ("verify-1",),
    )
    metadata = tmp_path / "metadata"
    MetadataStore(metadata).save_object(obj)
    return root, metadata, obj, path


def test_full_hash_verification_report_is_successful(tmp_path):
    root, metadata, _, _ = _fixture(tmp_path)
    report = verify_collection("aminet", root, metadata, "full-hashes")
    assert report.result == "success"
    assert report.file_count == 1
    assert report.fingerprint


def test_changed_file_is_reported_without_mutation(tmp_path):
    root, metadata, _, path = _fixture(tmp_path)
    before = path.read_bytes()
    path.write_bytes(b"changed")
    report = verify_collection("aminet", root, metadata, "sha256")
    assert "util/arc/example.lha" in report.hash_mismatches
    assert path.read_bytes() != before


def test_metadata_only_reconciliation_is_read_only(tmp_path):
    root, metadata, _, path = _fixture(tmp_path)
    before = path.stat().st_mtime_ns
    result = reconciliation("aminet", root, metadata)
    assert result["read_only"] is True
    assert path.stat().st_mtime_ns == before


def test_repair_plan_contains_metadata_actions_only(tmp_path):
    root, metadata, _, _ = _fixture(tmp_path)
    result = repair_plan("aminet", root, metadata)
    assert result["content_modification"] is False
    assert all("file" not in action["action"] or "metadata" in action["action"] for action in result["actions"])


def test_object_and_file_trace_are_read_only(tmp_path):
    root, metadata, obj, _ = _fixture(tmp_path)
    assert object_trace(obj.id, metadata)["found"]
    file_id = "util/arc/example.lha"
    trace = file_trace(file_id, metadata)
    assert trace["found"]
    assert trace["object_id"] == obj.id


def test_untracked_collection_file_is_detected(tmp_path):
    root, metadata, _, _ = _fixture(tmp_path)
    (root / "unexpected.txt").write_text("not metadata", encoding="utf-8")
    report = verify_collection("aminet", root, metadata, "metadata-only")
    assert "unexpected.txt" in report.untracked_files
