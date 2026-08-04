from pathlib import Path
import zipfile

import pytest

from scripts.preservation.external.models import ExternalSource
from scripts.preservation.external.mirror_execution import AcquisitionEntry, MirrorExecution, local_hashes, MirrorExecutionStore
from scripts.preservation.media_analysis import analyze_media
from scripts.preservation.media_import_plans import generate_import_plan, save_link
from scripts.preservation.aminet_import import validate_media_plan, execute_media_plan
from scripts.preservation.plans import PlanStore


def setup(tmp_path: Path):
    media = tmp_path / "media" / "aminet-cd" / "disk.zip"; media.parent.mkdir(parents=True)
    with zipfile.ZipFile(media, "w") as archive:
        archive.writestr("util/arc/example.lha", b"payload")
        archive.writestr("util/arc/example.readme", b"description")
    hashes, size = local_hashes(media)
    entry = AcquisitionEntry("entry", "exec", "mirror", "source", "item", "disk.zip", "", size, {}, "stage", str(media), "aminet-cd", "unknown", state="completed", local_hashes=hashes, bytes_downloaded=size)
    execution = MirrorExecution("exec", "mirror", "source", "snapshot", "fp", "completed", "", "", ("entry",), completed_entries=("entry",), resumable=False)
    source = ExternalSource("source", "Aminet", "", "internet-archive", "https://archive.org", "aminetcd", "aminet-cd", license_profile="unknown")
    analysis = analyze_media("media-id", entry, execution, source, "mirror", "snapshot", media_root=tmp_path / "media")
    metadata = tmp_path / "metadata"; MediaAnalysisStore = __import__("scripts.preservation.media_analysis", fromlist=["MediaAnalysisStore"]).MediaAnalysisStore; MediaAnalysisStore(metadata).save(analysis)
    MirrorExecutionStore(metadata).save_execution(execution); MirrorExecutionStore(metadata).save_entry(entry)
    plan = generate_import_plan(analysis, policy="aminet-content-and-readmes")
    PlanStore(metadata).save(plan); save_link(metadata, plan, analysis)
    return media, metadata, plan


def test_media_plan_validation_and_exact_import(tmp_path: Path):
    media, metadata, plan = setup(tmp_path)
    assert validate_media_plan(plan, metadata, tmp_path / "media") == ()
    copied, reused = execute_media_plan(plan, metadata, tmp_path / "aminet", tmp_path / "staging", tmp_path / "media", yes=True)
    assert copied == 2 and reused == 0
    assert (tmp_path / "aminet" / "aminet" / "util/arc/example.lha").exists() or (tmp_path / "aminet" / "util/arc/example.lha").exists()
    assert media.read_bytes() == media.read_bytes()


def test_media_plan_requires_confirmation(tmp_path: Path):
    _, metadata, plan = setup(tmp_path)
    with pytest.raises(PermissionError): execute_media_plan(plan, metadata, tmp_path / "aminet", tmp_path / "stage", tmp_path / "media", yes=False)
