from pathlib import Path
import io
import json

import pytest

from scripts.preservation.external.models import ExternalFile, ExternalItem, ExternalSource
from scripts.preservation.external.registry import DEFAULT_SOURCES, ExternalSourceStore, validate_source
from scripts.preservation.external.snapshots import create_snapshot, SnapshotStore
from scripts.preservation.external.changes import diff_snapshots
from scripts.preservation.external.mirror_plans import create_mirror_plan, safe_name
from scripts.preservation.external.internet_archive import InternetArchiveProvider


def test_default_sources_and_duplicate_rejection(tmp_path: Path) -> None:
    store = ExternalSourceStore(tmp_path)
    store.seed_defaults()
    assert {source.upstream_identifier for source in store.list()} == {"amiga_cdrom", "softwarecapsules_commodore", "aminetcd", "commodore-amiga-collections-fred-fish"}
    with pytest.raises(ValueError):
        store.save(DEFAULT_SOURCES[0])


def test_external_source_endpoint_validation() -> None:
    validate_source(DEFAULT_SOURCES[0])
    with pytest.raises(ValueError):
        validate_source(ExternalSource("x", "x", "", "internet-archive", "file:///tmp", "x", "unknown"))


def test_snapshot_fingerprint_is_deterministic(tmp_path: Path) -> None:
    item = ExternalItem("item", files=(ExternalFile("disk.adf", 4, "ADF", "original", "abc"),))
    one = create_snapshot("source", "internet-archive", "check", {"identifier": "source"}, (item,))
    two = create_snapshot("source", "internet-archive", "check", {"identifier": "source"}, (item,))
    assert one.fingerprint == two.fingerprint
    SnapshotStore(tmp_path).save(one)
    assert SnapshotStore(tmp_path).list("source")[0]["id"] == one.id


def test_snapshot_diff_detects_new_removed_and_changed() -> None:
    old = create_snapshot("s", "internet-archive", "a", {}, (ExternalItem("old"), ExternalItem("same", title="a")))
    new = create_snapshot("s", "internet-archive", "b", {}, (ExternalItem("new"), ExternalItem("same", title="b")))
    types = {change["type"] for change in diff_snapshots(old, new)["changes"]}
    assert types == {"new", "removed-upstream", "metadata-changed"}


def test_mirror_plan_excludes_derivatives_and_torrents() -> None:
    item = ExternalItem("item", files=(ExternalFile("disk.adf", 4, classification="original"), ExternalFile("disk_thumb.jpg", 1, classification="derivative"), ExternalFile("item.torrent", 1)))
    plan = create_mirror_plan("s", create_snapshot("s", "internet-archive", "c", {}, (item,)))
    assert [file["filename"] for file in plan.selected_files] == ["disk.adf"]
    assert len(plan.excluded_files) == 2


def test_unsafe_names_rejected() -> None:
    assert safe_name("disk.adf")
    assert not safe_name("../disk.adf")
    assert not safe_name("/absolute")
    assert not safe_name("bad\nname")


class FakeResponse:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return json.dumps(self.value).encode()


def test_internet_archive_provider_normalizes_metadata_without_download() -> None:
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        if "advancedsearch" in request.full_url:
            return FakeResponse({"response": {"numFound": 1, "docs": [{"identifier": "item"}]}})
        return FakeResponse({"metadata": {"title": "Item", "mediatype": "data"}, "files": [{"name": "disk.adf", "size": "4", "md5": "abc"}]})
    metadata, items, complete = InternetArchiveProvider(opener=opener).inspect(DEFAULT_SOURCES[2], page_size=5)
    assert complete and items[0].files[0].upstream_hashes == "upstream-reported"
    assert all(url.startswith("https://archive.org/") for url in calls)


def test_provider_rejects_non_official_url() -> None:
    provider = InternetArchiveProvider(opener=lambda *_: None)
    with pytest.raises(ValueError):
        provider._get("https://example.invalid/metadata")
