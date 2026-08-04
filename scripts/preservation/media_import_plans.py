"""Generate ordinary draft import plans from immutable media analyses."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from .media_analysis import MediaAnalysis
from .plans import ImportPlan, create_plan, PlanStore
from .external.storage import ExternalStorage, stable_id


def generate_import_plan(analysis: MediaAnalysis, *, policy: str = "all-safe-members", collection: str | None = None) -> ImportPlan:
    if analysis.blocking_findings or analysis.recommended_import_mode in {"unsupported", "manual-review"}:
        raise ValueError("media analysis requires manual review before plan generation")
    selected = tuple(member.original_relative_path for member in analysis.members if member.eligible and not member.unsafe)
    if policy == "aminet-content-and-readmes":
        selected = tuple(path for path in selected if Path(path).suffix.lower() not in {".info", ".nfo"})
    elif policy == "documentation-only":
        selected = tuple(path for path in selected if Path(path).suffix.lower() in {".readme", ".txt", ".pdf", ".guide", ".doc"})
    if policy == "manual-selection":
        selected = ()
    if not selected: raise ValueError("analysis produced no safe selected entries")
    destination = collection or (analysis.candidate_collections[0]["collection"] if analysis.candidate_collections else "source")
    plan = create_plan(f"media:{analysis.media_id}", analysis.local_media_hashes["sha256"], analysis.container_type, destination, selected, analysis.recommended_import_mode, (policy,))
    return plan


def save_link(metadata_root: Path, plan: ImportPlan, analysis: MediaAnalysis) -> None:
    ExternalStorage(metadata_root).put("media-import-plan-links", plan.id, {"plan_id": plan.id, "analysis_id": analysis.id, "media_id": analysis.media_id, "acquisition_execution_id": analysis.acquisition_execution_id, "acquisition_entry_id": analysis.acquisition_entry_id, "mirror_plan_id": analysis.mirror_plan_id, "external_source_id": analysis.external_source_id, "snapshot_id": analysis.snapshot_id, "local_media_path": analysis.local_media_path, "analysis_fingerprint": analysis.fingerprint, "import_approval_required": True})
