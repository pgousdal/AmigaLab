"""Offline execution bridge from media analyses to the existing importer."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .external.mirror_execution import MirrorExecutionStore, local_hashes
from .external.registry import ExternalSourceStore
from .media_analysis import MediaAnalysisStore
from .media_import_plans import generate_import_plan
from .models import Source
from .plans import ImportPlan
from .storage import MetadataStore
from .importer import import_selected


def _link(root: Path, plan_id: str) -> dict[str, object]:
    import json
    directory = root / "media-import-plan-links"
    for path in directory.glob("*.json") if directory.is_dir() else ():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("plan_id") == plan_id:
            return data
    raise ValueError("media-generated import-plan link is missing")


def validate_media_plan(plan: ImportPlan, metadata_root: Path, media_root: Path) -> tuple[str, ...]:
    issues: list[str] = []
    try:
        link = _link(metadata_root, plan.id)
        analysis = MediaAnalysisStore(metadata_root).get(str(link["analysis_id"]))
    except (OSError, ValueError, KeyError) as error:
        return (f"media analysis link unavailable: {error}",)
    path = Path(analysis.local_media_path)
    if not path.is_file() or not path.resolve().is_relative_to(media_root.resolve()): issues.append("media path missing or outside media root")
    elif local_hashes(path)[0] != analysis.local_media_hashes: issues.append("local media hash changed")
    if analysis.fingerprint != link.get("analysis_fingerprint"): issues.append("analysis fingerprint mismatch")
    if plan.source_id != f"media:{analysis.media_id}": issues.append("plan source is not the acquired media")
    if plan.destination_collection != "aminet" and "aminet" in [str(item.get("collection")) for item in analysis.candidate_collections]: issues.append("Aminet analysis must target aminet collection")
    selected = set(plan.selected_entries); approved = {member.original_relative_path for member in analysis.members if member.eligible and not member.unsafe}
    if not selected.issubset(approved): issues.append("selected entries differ from analysis members")
    if plan.status in {"cancelled", "superseded", "executing", "completed"}: issues.append(f"plan status is {plan.status}")
    return tuple(sorted(set(issues)))


def execute_media_plan(plan: ImportPlan, metadata_root: Path, archive_root: Path, staging_root: Path, media_root: Path, *, yes: bool) -> tuple[int, int]:
    if not yes: raise PermissionError("import execution requires --yes")
    issues = validate_media_plan(plan, metadata_root, media_root)
    if issues: raise ValueError("media import plan validation failed: " + "; ".join(issues))
    link = _link(metadata_root, plan.id)
    analysis = MediaAnalysisStore(metadata_root).get(str(link["analysis_id"]))
    execution = MirrorExecutionStore(metadata_root).load_execution(analysis.acquisition_execution_id)
    entry = MirrorExecutionStore(metadata_root).load_entry(analysis.acquisition_entry_id)
    source = Source(f"media:{analysis.media_id}", f"Acquired {analysis.media_id}", analysis.container_type, analysis.local_media_path, analysis.license_profile, "unknown", f"mirror execution {execution.id}")
    store = MetadataStore(metadata_root)
    return import_selected(Path(analysis.local_media_path), plan.destination_collection, source, tuple(plan.selected_entries), store, archive_root, staging_root, transaction_id=f"import-{plan.id}")
