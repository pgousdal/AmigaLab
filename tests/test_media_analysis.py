from pathlib import Path
import zipfile

import pytest

from scripts.preservation.external.models import ExternalSource
from scripts.preservation.external.mirror_execution import AcquisitionEntry, MirrorExecution, local_hashes
from scripts.preservation.media_analysis import analyze_media, detect_container, MediaAnalysisStore
from scripts.preservation.media_import_plans import generate_import_plan, save_link


def case(tmp_path: Path, unsafe: bool = True):
    media = tmp_path / "media" / "aminet-cd" / "disk" / "disk.zip"; media.parent.mkdir(parents=True)
    with zipfile.ZipFile(media, "w") as archive:
        archive.writestr("util/arc/example.lha", b"archive")
        archive.writestr("util/arc/example.readme", b"readme")
        if unsafe: archive.writestr("../unsafe", b"bad")
    hashes, size = local_hashes(media)
    entry = AcquisitionEntry("entry", "exec", "mirror", "source", "item", "disk.zip", "https://archive.org/download/item/disk.zip", size, {}, str(tmp_path / "stage"), str(media), "aminet-cd", "unknown", state="completed", local_hashes=hashes, bytes_downloaded=size)
    execution = MirrorExecution("exec", "mirror", "source", "snapshot", "fp", "completed", "", "", ("entry",), completed_entries=("entry",), resumable=False)
    source = ExternalSource("source", "Aminet", "", "internet-archive", "https://archive.org", "aminetcd", "aminet-cd", license_profile="unknown")
    return media, entry, execution, source


def test_container_detection_and_aminet_analysis(tmp_path: Path) -> None:
    media, entry, execution, source = case(tmp_path)
    assert detect_container(media)[0] == "zip"
    analysis = analyze_media("media-id", entry, execution, source, "mirror", "snapshot", media_root=tmp_path / "media")
    assert analysis.recommended_import_mode == "manual-review"
    assert analysis.candidate_collections[0]["collection"] == "aminet"
    assert any(group["sidecar"].endswith(".readme") for group in analysis.sidecar_groups)
    assert "../unsafe" in analysis.unsafe_entries


def test_analysis_is_deterministic_and_read_only(tmp_path: Path) -> None:
    media, entry, execution, source = case(tmp_path)
    before = media.read_bytes()
    first = analyze_media("media-id", entry, execution, source, "mirror", "snapshot", media_root=tmp_path / "media")
    second = analyze_media("media-id", entry, execution, source, "mirror", "snapshot", media_root=tmp_path / "media")
    assert first.fingerprint == second.fingerprint and media.read_bytes() == before


def test_incomplete_or_damaged_acquisition_rejected(tmp_path: Path) -> None:
    media, entry, execution, source = case(tmp_path)
    with pytest.raises(ValueError): analyze_media("id", entry.__class__(**{**entry.__dict__, "state": "failed"}), execution, source, "m", "s", media_root=tmp_path / "media")
    media.write_bytes(b"changed")
    with pytest.raises(ValueError): analyze_media("id", entry, execution, source, "m", "s", media_root=tmp_path / "media")


def test_import_plan_is_draft_and_linked(tmp_path: Path) -> None:
    media, entry, execution, source = case(tmp_path, unsafe=False)
    analysis = analyze_media("media-id", entry, execution, source, "mirror", "snapshot", media_root=tmp_path / "media")
    plan = generate_import_plan(analysis, policy="aminet-content-and-readmes")
    assert plan.status == "draft" and "util/arc/example.lha" in plan.selected_entries
    save_link(tmp_path / "metadata", plan, analysis)
    assert (tmp_path / "metadata" / "media-import-plan-links").is_dir()


def test_unknown_regular_media_is_conservative(tmp_path: Path) -> None:
    media, entry, execution, source = case(tmp_path)
    media.write_bytes(b"not an archive")
    hashes, size = local_hashes(media)
    entry = entry.__class__(**{**entry.__dict__, "local_hashes": hashes, "bytes_downloaded": size, "expected_size": size})
    analysis = analyze_media("id", entry, execution, source, "m", "s", media_root=tmp_path / "media")
    assert analysis.recommended_import_mode == "media-only"
