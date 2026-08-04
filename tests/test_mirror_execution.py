from pathlib import Path
import io

import pytest

from scripts.preservation.external.models import ExternalFile, ExternalItem, ExternalSource
from scripts.preservation.external.snapshots import create_snapshot
from scripts.preservation.external.mirror_plans import create_mirror_plan
from scripts.preservation.external.mirror_execution import (
    AcquisitionHttpClient, MirrorExecutionStore, create_execution, execute_mirror,
    local_hashes, validate_content_url, validate_upstream,
)


class Response:
    status = 200
    headers = {}
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self, size=-1):
        if not self.body: return b""
        value, self.body = self.body[:size], self.body[size:]
        return value
    def geturl(self): return "https://archive.org/download/item/disk.adf"


def case(tmp_path: Path):
    source = ExternalSource("source", "source", "", "internet-archive", "https://archive.org", "collection", "aminet-cd", license_profile="unknown")
    snapshot = create_snapshot("source", "internet-archive", "check", {}, (ExternalItem("item", files=(ExternalFile("disk.adf", 7, md5="321c3cf486ed509164edec1e1981fec8", locator="https://archive.org/download/item/disk.adf"),)),))
    plan = create_mirror_plan("source", snapshot)
    plan = type(plan)(**{**plan.__dict__, "status": "approved", "approval_history": ("approval",)})
    return source, plan


def test_content_url_policy() -> None:
    validate_content_url("https://archive.org/download/x/file")
    with pytest.raises(ValueError): validate_content_url("http://archive.org/file")
    with pytest.raises(ValueError): validate_content_url("https://example.invalid/file")


def test_four_hashes_and_upstream_validation(tmp_path: Path) -> None:
    path = tmp_path / "x"; path.write_bytes(b"payload")
    hashes, size = local_hashes(path)
    assert size == 7 and set(hashes) == {"md5", "sha1", "sha256", "sha512"}
    assert validate_upstream({"md5": hashes["md5"]}, hashes) == "matched"
    assert validate_upstream({"md5": "bad"}, hashes) == "mismatched"


def test_execution_requires_approval(tmp_path: Path) -> None:
    source, plan = case(tmp_path)
    plan = type(plan)(**{**plan.__dict__, "approval_history": ()})
    with pytest.raises(ValueError): execute_mirror(plan, source, MirrorExecutionStore(tmp_path / "metadata"), tmp_path / "staging", tmp_path / "media", yes=True)


def test_approved_execution_streams_and_places_media(tmp_path: Path) -> None:
    source, plan = case(tmp_path)
    client = AcquisitionHttpClient(opener=lambda request, timeout: Response(b"payload"))
    execution = execute_mirror(plan, source, MirrorExecutionStore(tmp_path / "metadata"), tmp_path / "staging", tmp_path / "media", yes=True, client=client)
    assert execution.state == "completed"
    assert (tmp_path / "media" / "unknown" / plan.id / "disk.adf").read_bytes() == b"payload"


def test_execution_without_confirmation_does_not_write(tmp_path: Path) -> None:
    source, plan = case(tmp_path)
    with pytest.raises(PermissionError): execute_mirror(plan, source, MirrorExecutionStore(tmp_path / "metadata"), tmp_path / "staging", tmp_path / "media", yes=False)
    assert not (tmp_path / "media").exists()


def test_execution_reuses_identical_destination(tmp_path: Path) -> None:
    source, plan = case(tmp_path)
    destination = tmp_path / "media" / "unknown" / plan.id / "disk.adf"; destination.parent.mkdir(parents=True); destination.write_bytes(b"payload")
    execution = execute_mirror(plan, source, MirrorExecutionStore(tmp_path / "metadata"), tmp_path / "staging", tmp_path / "media", yes=True, client=AcquisitionHttpClient(opener=lambda *_: (_ for _ in ()).throw(AssertionError("downloaded"))))
    assert execution.state == "completed" and execution.reused_entries


def test_different_destination_blocks(tmp_path: Path) -> None:
    source, plan = case(tmp_path)
    destination = tmp_path / "media" / "unknown" / plan.id / "disk.adf"; destination.parent.mkdir(parents=True); destination.write_bytes(b"different")
    execution = execute_mirror(plan, source, MirrorExecutionStore(tmp_path / "metadata"), tmp_path / "staging", tmp_path / "media", yes=True, client=AcquisitionHttpClient(opener=lambda *_: (_ for _ in ()).throw(AssertionError("downloaded"))))
    assert execution.state == "blocked"


def test_staging_is_transaction_namespaced(tmp_path: Path) -> None:
    source, plan = case(tmp_path)
    execution, entries = create_execution(plan, source, tmp_path / "staging", tmp_path / "media")
    assert str(tmp_path / "staging" / "mirror-executions" / execution.id) in entries[0].staging_path
