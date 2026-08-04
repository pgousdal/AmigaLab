from pathlib import Path

import pytest

from scripts.preservation.external.checks import InspectionStore, CheckpointStore, checkpoint_from_items, inspect_resumable, new_check
from scripts.preservation.external.models import ExternalFile, ExternalItem, ExternalSource
from scripts.preservation.external.snapshots import create_snapshot
from scripts.preservation.external.mirror_plans import create_mirror_plan, validate_mirror_plan, review_mirror_plan


class Pages:
    def __init__(self): self.calls = []
    def inspect(self, source, *, page_size, page):
        self.calls.append(page)
        if page == 1: return {}, (ExternalItem("one", files=(ExternalFile("one.adf", 2),)),), False
        return {}, (ExternalItem("two", files=(ExternalFile("two.adf", 3),)),), True


def test_resumable_inspection_checkpoints_each_page(tmp_path: Path) -> None:
    source = ExternalSource("s", "S", "", "internet-archive", "https://archive.org", "collection", "unknown")
    store = InspectionStore(tmp_path)
    store.save(new_check("s", "internet-archive", "check"))
    provider = Pages()
    result = inspect_resumable(source, provider, store, "check", page_size=1)
    assert result.status == "completed" and provider.calls == [1, 2]
    assert len(CheckpointStore(tmp_path).list("check")) == 2


def test_interrupted_inspection_resumes_without_duplicate_pages(tmp_path: Path) -> None:
    source = ExternalSource("s", "S", "", "internet-archive", "https://archive.org", "collection", "unknown")
    store = InspectionStore(tmp_path); store.save(new_check("s", "internet-archive", "check"))
    class Interrupt:
        def __init__(self): self.calls = []
        def inspect(self, source, *, page_size, page):
            self.calls.append(page)
            if page == 1: return {}, (ExternalItem("one"),), False
            raise TimeoutError("temporary")
    provider = Interrupt(); assert inspect_resumable(source, provider, store, "check").status == "interrupted"
    assert len(CheckpointStore(tmp_path).list("check")) == 1
    provider2 = Pages(); result = inspect_resumable(source, provider2, store, "check")
    assert result.status == "completed" and provider2.calls == [2]


def test_checkpoint_fingerprint_is_stable(tmp_path: Path) -> None:
    items = (ExternalItem("x", files=(ExternalFile("x.adf", 1),)),)
    assert checkpoint_from_items("c", "s", "p", 1, items).fingerprint == checkpoint_from_items("c", "s", "p", 1, items).fingerprint


def test_mirror_plan_validation_and_review(tmp_path: Path) -> None:
    item = ExternalItem("x", files=(ExternalFile("x.adf", 2, md5="a"),))
    snapshot = create_snapshot("s", "internet-archive", "c", {}, (item,))
    plan = create_mirror_plan("s", snapshot)
    assert validate_mirror_plan(plan, snapshot) == ()
    assert review_mirror_plan(plan)["selected_file_count"] == 1


def test_cancelled_or_superseded_mirror_plan_invalid() -> None:
    snapshot = create_snapshot("s", "internet-archive", "c", {}, (ExternalItem("x"),))
    plan = create_mirror_plan("s", snapshot)
    cancelled = type(plan)(**{**plan.__dict__, "status": "cancelled"})
    assert "plan status is cancelled" in validate_mirror_plan(cancelled, snapshot)
