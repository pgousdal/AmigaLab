#!/usr/bin/env python3
"""Metadata-first, non-destructive import command for AmigaLab."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys

from preservation.importer import SUPPORTED_SOURCE_KINDS, import_selected, import_source, scan
from preservation.conflicts import conflict_report
from preservation.media import discover_candidates, register_media
from preservation.models import Source
from preservation.storage import MetadataStore
from preservation.transactions import TransactionStore, new_transaction, source_fingerprint
from preservation.policy import validate_license_profile
from preservation.plans import PlanStore, create_plan
from preservation.recovery import RecoveryExecutor
from preservation.recovery_workflow import RecoveryPlanStore, AuditReportStore, RecoveryOrchestrator, generate_plan, dry_run
from preservation.verification import append_verification, verify_object
from preservation.external.models import ExternalSource
from preservation.external.registry import ExternalSourceStore
from preservation.external.internet_archive import InternetArchiveProvider
from preservation.external.snapshots import SnapshotStore, create_snapshot
from preservation.external.changes import diff_snapshots
from preservation.external.mirror_plans import MirrorPlanStore, create_mirror_plan
from preservation.external.mirror_plans import validate_mirror_plan, review_mirror_plan
from preservation.external.checks import InspectionStore, inspect_resumable
from preservation.external.mirror_execution import MirrorExecutionStore, execute_mirror, resume_mirror, local_hashes
from preservation.media_analysis import MediaAnalysisStore, analyze_media
from preservation.media_import_plans import generate_import_plan, save_link
from preservation.aminet_import import validate_media_plan, execute_media_plan
from preservation.external.storage import ExternalStorage
from preservation.verification_reports import verify_collection, VerificationReportStore, reconciliation, repair_plan
from preservation.traces import object_trace, file_trace, media_trace as enriched_media_trace
from preservation.relationship_backfill import create_plan as create_relationship_backfill_plan
from preservation.operations import OperationsRun, OperationsStore, OperationsLock, operations_preview, retention_plan, validate_operations_config, now
from preservation.catalog import build_catalog, CatalogIndex, verify_catalog
from preservation.web import WebConfig, create_app, run as run_web
from preservation.catalog.builder import build_documents
from preservation.catalog.meilisearch import MeiliClient, validate_endpoint
from preservation.version import __version__


def roots(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    archive_root = Path(args.archive_root)
    return archive_root, Path(args.metadata_root), Path(args.staging_root)


def print_preview(preview: object) -> None:
    for label, value in (
        ("New objects", preview.new_objects),
        ("Existing objects", preview.existing_objects),
        ("Changed", preview.changed),
        ("Conflicts", preview.conflicts),
    ):
        print(f"{label}: {value}")


def command_source_add(args: argparse.Namespace) -> int:
    if args.kind not in SUPPORTED_SOURCE_KINDS:
        raise ValueError(f"Unsupported source kind: {args.kind}")
    validate_license_profile(args.license_profile)
    _, metadata_root, _ = roots(args)
    store = MetadataStore(metadata_root)
    store.save_source(Source(args.id, args.name, args.kind, args.location, args.license_profile, args.media_classification, args.notes))
    print(f"Registered source: {args.id}")
    return 0


def command_scan(args: argparse.Namespace) -> int:
    archive_root, metadata_root, _ = roots(args)
    collection = args.collection or Path(args.location).name.lower()
    print_preview(scan(Path(args.location), collection, MetadataStore(metadata_root), archive_root))
    return 0


def command_import(args: argparse.Namespace) -> int:
    archive_root, metadata_root, staging_root = roots(args)
    store = MetadataStore(metadata_root)
    source = store.get_source(args.source)
    if source is None:
        raise ValueError(f"Unknown source ID: {args.source}. Register it with source-add first.")
    location = Path(args.location)
    preview = scan(location, args.collection, store, archive_root)
    transaction = new_transaction(source.id, source_fingerprint(location), args.collection, "import", preview.relative_paths)
    TransactionStore(metadata_root).save(transaction)
    try:
        print_preview(import_source(location, args.collection, source, store, archive_root, staging_root, args.yes))
    except Exception:
        TransactionStore(metadata_root).update(transaction, phase="failed", result="failed")
        raise
    TransactionStore(metadata_root).update(transaction, phase="completed", completed_entries=preview.relative_paths, pending_entries=(), result="success")
    return 0


def command_transaction_status(args: argparse.Namespace) -> int:
    transaction = TransactionStore(Path(args.metadata_root)).load(args.transaction_id)
    entries = TransactionStore(Path(args.metadata_root)).list_entries(transaction.id)
    summary = TransactionStore(Path(args.metadata_root)).summary(transaction.id)
    print(f"transaction: {transaction.id}\nphase: {transaction.phase}\nentries: {summary['total']}\ncompleted: {summary['completed']}\nreused: {summary['reused']}\nfailed: {summary['failed']}\nattempts: {summary['attempts']}")
    return 0


def command_transaction_reconcile(args: argparse.Namespace) -> int:
    store = TransactionStore(Path(args.metadata_root))
    transaction = store.load(args.transaction_id)
    summary = store.summary(transaction.id)
    print(json.dumps({"transaction_id": transaction.id, "summary": summary, "reconciliation": "read-only"}, indent=2, sort_keys=True))
    return 0


def command_transaction_resume(args: argparse.Namespace) -> int:
    metadata_root = Path(args.metadata_root)
    store = MetadataStore(metadata_root)
    transaction = TransactionStore(metadata_root).load(args.transaction_id)
    if getattr(args, "plan_only", False):
        print(json.dumps(TransactionStore(metadata_root).recovery_plan(transaction.id), indent=2, sort_keys=True))
        return 0
    if not args.yes:
        print(f"resume requires confirmation: {transaction.id}", file=sys.stderr)
        return 1
    source = store.get_source(transaction.source_id)
    if source is None:
        raise ValueError(f"source metadata is missing: {transaction.source_id}")
    location = Path(source.locator)
    if source_fingerprint(location) != transaction.source_fingerprint:
        raise ValueError("source changed since transaction scan; resume refused")
    entries = TransactionStore(metadata_root).list_entries(transaction.id)
    selected = tuple(entry.source_path for entry in entries if entry.state not in {"completed", "reused", "skipped"}) or transaction.pending_entries
    copied, reused = import_selected(location, transaction.destination_collection, source, selected, store, Path(args.archive_root), Path(args.staging_root), transaction.id)
    print(f"resumed: {transaction.id}\ncopied: {copied}\nreused: {reused}")
    TransactionStore(metadata_root).update(transaction, phase="completed", result="success")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    archive_root, metadata_root, _ = roots(args)
    collection_name = getattr(args, "collection_name", None) or args.collection
    store = MetadataStore(metadata_root)
    failures = 0
    for object_ in store.list_objects():
        if object_.original_collection != collection_name:
            continue
        event = verify_object(object_, archive_root / collection_name, args.algorithm)
        store.save_verification(event)
        store.save_object(append_verification(object_, event))
        if not event.success:
            failures += 1
    print(f"Verified collection {collection_name}: {failures} failed object(s)")
    return 1 if failures else 0


def command_media_scan(args: argparse.Namespace) -> int:
    from preservation.sources import adapter_for
    adapter = adapter_for(Path(args.location), args.kind)
    try:
        entries = list(adapter.entries())
        print(f"Media entries: {len(entries)}")
        for entry in entries:
            if entry.unsupported_reason:
                print(f"unsupported: {entry.path}: {entry.unsupported_reason}")
            else:
                print(f"{entry.path}\t{entry.size}")
    finally:
        adapter.close()
    return 0


def command_media_import(args: argparse.Namespace) -> int:
    if not args.yes:
        raise PermissionError("media import requires explicit confirmation: pass --yes")
    _, metadata_root, _ = roots(args)
    store = MetadataStore(metadata_root)
    media = register_media(Path(args.location), args.source, args.title, args.license_profile, notes=args.notes)
    media_destination = Path(args.media_root) / ("unknown" if media.license_profile == "unknown" else media.license_profile) / media.original_filename
    media_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.location, media_destination)
    store.save_media(media)
    print(f"Registered original media: {media.id}")
    return 0


def command_discover(args: argparse.Namespace) -> int:
    for candidate in discover_candidates(Path(args.location)):
        print(candidate)
    return 0


def command_conflict_report(args: argparse.Namespace) -> int:
    import json
    _, metadata_root, _ = roots(args)
    report = conflict_report(Path(args.location), args.collection, Path(args.archive_root), args.source, MetadataStore(metadata_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report else 0


def command_plan_create(args: argparse.Namespace) -> int:
    _, metadata_root, _ = roots(args)
    selected = tuple(args.paths or [])
    if not selected:
        selected = tuple(entry.path for entry in __import__('preservation.sources', fromlist=['adapter_for']).adapter_for(Path(args.location), args.kind).entries() if entry.is_file)
    plan = create_plan(args.source, source_fingerprint(Path(args.location)), args.kind or "directory", args.collection, selected, args.mode, tuple(args.include or []) + tuple(args.exclude or []))
    PlanStore(metadata_root).save(plan)
    print(plan.id)
    return 0


def command_plan_show(args: argparse.Namespace) -> int:
    print(PlanStore(Path(args.metadata_root)).load(args.plan_id))
    return 0


def command_plan_approve(args: argparse.Namespace) -> int:
    store = PlanStore(Path(args.metadata_root))
    plan = store.load(args.plan_id)
    if plan.conflicts or plan.status in {"cancelled", "superseded"}:
        raise ValueError("plan has unresolved conflicts")
    store.event(plan, "approval", args.note)
    store.update(plan, status="approved")
    print(f"approved: {plan.id}")
    return 0


def command_plan_validate(args: argparse.Namespace) -> int:
    plan = PlanStore(Path(args.metadata_root)).load(args.plan_id)
    diagnostics = []
    if plan.source_id.startswith("media:"):
        diagnostics.extend(validate_media_plan(plan, Path(args.metadata_root), Path(args.archive_root) / "media"))
    if plan.status in {"cancelled", "superseded", "completed"}:
        diagnostics.append(f"plan status is {plan.status}")
    if plan.import_mode not in {"media-only", "members-only", "media-and-members"}:
        diagnostics.append("invalid import mode")
    if any(Path(path).is_absolute() or ".." in Path(path).parts for path in plan.selected_entries):
        diagnostics.append("unsafe selected path")
    if plan.conflicts:
        diagnostics.append("unresolved conflicts present")
    if diagnostics:
        print("invalid: " + "; ".join(diagnostics), file=sys.stderr)
        return 1
    print("valid")
    return 0


def command_plan_cancel(args: argparse.Namespace) -> int:
    store = PlanStore(Path(args.metadata_root))
    plan = store.load(args.plan_id)
    if plan.status not in {"draft", "ready", "blocked", "approved"}:
        raise ValueError("only draft, ready, blocked, or approved plans may be cancelled")
    store.event(plan, "cancellation", args.reason)
    store.update(plan, status="cancelled")
    return 0


def command_plan_execute(args: argparse.Namespace) -> int:
    if not args.yes:
        raise PermissionError("plan execution requires explicit confirmation: pass --yes")
    metadata_root = Path(args.metadata_root)
    store = PlanStore(metadata_root)
    plan = store.load(args.plan_id)
    if plan.status != "approved":
        raise ValueError("plan must be approved before execution")
    if plan.source_id.startswith("media:"):
        copied, reused = execute_media_plan(plan, metadata_root, Path(args.archive_root), Path(args.staging_root), Path(args.media_root), yes=True)
        print(f"transaction: import-{plan.id}\ncopied: {copied}\nreused: {reused}")
        return 0
    if command_plan_validate(argparse.Namespace(plan_id=args.plan_id, metadata_root=str(metadata_root))) != 0:
        raise ValueError("plan validation failed")
    source = MetadataStore(metadata_root).get_source(plan.source_id)
    if source is None:
        raise ValueError("plan source is not registered")
    if source_fingerprint(Path(source.locator)) != plan.source_fingerprint:
        raise ValueError("source fingerprint changed since plan creation")
    if plan.import_mode == "media-only":
        if Path(source.locator).is_dir():
            raise ValueError("media-only requires a single media or archive source")
        media = register_media(Path(source.locator), source.id, Path(source.locator).name, source.license_profile, source.media_classification)
        media_path = Path(args.media_root) / (source.media_classification or "unknown") / media.id / media.original_filename
        media_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.locator, media_path)
        MetadataStore(metadata_root).save_media(media)
        print(f"media preserved: {media_path}")
        return 0
    store.event(plan, "execution-start", "approved plan execution")
    transaction = new_transaction(source.id, plan.source_fingerprint, plan.destination_collection, plan.import_mode, plan.selected_entries)
    transaction_store = TransactionStore(metadata_root)
    transaction_store.save(transaction)
    transaction_store.update(transaction, phase="copying")
    copied, reused = import_selected(Path(source.locator), plan.destination_collection, source, plan.selected_entries, MetadataStore(metadata_root), Path(args.archive_root), Path(args.staging_root))
    transaction_store.update(transaction, phase="completed", completed_entries=plan.selected_entries, pending_entries=(), result="success")
    print(f"transaction: {transaction.id}\ncopied: {copied}\nreused: {reused}\nstatus: completed")
    return 0


def command_conflict_list(args: argparse.Namespace) -> int:
    plan = PlanStore(Path(args.metadata_root)).load(args.plan_id)
    import json
    print(json.dumps(list(plan.conflicts), indent=2, sort_keys=True))
    return 0


def command_conflict_decide(args: argparse.Namespace) -> int:
    if args.action not in {"unresolved", "skip", "reuse-identical", "record-provenance-only", "import-with-alternate-target", "abort-plan"}:
        raise ValueError("unsupported conflict action")
    store = PlanStore(Path(args.metadata_root))
    plan = store.load(args.plan_id)
    store.event(plan, "conflict-decision", f"{args.conflict_id}: {args.action}: {args.reason}")
    print(f"recorded decision for {args.conflict_id}")
    return 0


def command_recovery_plan(args: argparse.Namespace) -> int:
    metadata_root = Path(args.metadata_root)
    transaction_store = TransactionStore(metadata_root)
    transaction = transaction_store.load(args.transaction_id)
    entries = transaction_store.list_entries(transaction.id)
    plan = generate_plan(entries, transaction.source_fingerprint, transaction.id,
                         Path(args.source_path or ""), Path(args.staging_root),
                         Path(args.archive_root) / transaction.destination_collection)
    if args.write:
        RecoveryPlanStore(metadata_root).save(plan)
    print(plan.to_json())
    return 0


def command_recovery_dry_run(args: argparse.Namespace) -> int:
    metadata_root = Path(args.metadata_root)
    plan = RecoveryPlanStore(metadata_root).load(args.plan_id)
    entries = TransactionStore(metadata_root).list_entries(plan.identity)
    report = dry_run(plan, entries, Path(args.staging_root), Path(plan.destination_path))
    if getattr(args, "write_report", False):
        AuditReportStore(metadata_root).save(report)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0 if report.result == "ready" else 1


def command_recovery_report(args: argparse.Namespace) -> int:
    path = Path(args.metadata_root) / "recovery-reports" / f"{args.report_id}.json"
    print(path.read_text(encoding="utf-8"))
    return 0


def command_recovery_execute(args: argparse.Namespace) -> int:
    metadata_root = Path(args.metadata_root)
    plan = RecoveryPlanStore(metadata_root).load(args.plan_id)
    entries = TransactionStore(metadata_root).list_entries(plan.identity)
    result = RecoveryOrchestrator(metadata_root).execute(plan, entries, source=Path(plan.source_path) if plan.source_path else None)
    print(json.dumps(asdict(result.report), indent=2, sort_keys=True) if args.json else result.report.human())
    return {"completed": 0, "completed_with_skips": 1, "blocked": 2, "stale": 2, "failed": 3}.get(result.status, 3)


def command_recovery_resume(args: argparse.Namespace) -> int:
    metadata_root = Path(args.metadata_root)
    plan = RecoveryPlanStore(metadata_root).load(args.plan_id)
    entries = TransactionStore(metadata_root).list_entries(plan.identity)
    result = RecoveryOrchestrator(metadata_root).resume(plan, args.execution_id, entries, source=Path(plan.source_path) if plan.source_path else None)
    print(json.dumps(asdict(result.report), indent=2, sort_keys=True) if args.json else result.report.human())
    return {"completed": 0, "completed_with_skips": 1, "blocked": 2, "stale": 2, "failed": 3}.get(result.status, 3)


def external_source_store(args: argparse.Namespace) -> ExternalSourceStore:
    return ExternalSourceStore(Path(args.metadata_root))


def command_external_source_add(args: argparse.Namespace) -> int:
    source = ExternalSource(args.id, args.name, args.description, "internet-archive", args.locator, args.upstream_identifier, args.target, tuple(args.platform_tag), tuple(args.content_tag), args.license_profile, args.media_classification)
    external_source_store(args).save(source)
    print(source.id)
    return 0


def command_external_source_list(args: argparse.Namespace) -> int:
    sources = [asdict(source) for source in external_source_store(args).list()]
    print(json.dumps(sources, indent=2, sort_keys=True) if args.json else "\n".join(f"{item['id']}\t{item['upstream_identifier']}\t{item['target']}" for item in sources))
    return 0


def command_external_source_show(args: argparse.Namespace) -> int:
    print(json.dumps(asdict(external_source_store(args).get(args.source_id)), indent=2, sort_keys=True))
    return 0


def command_external_source_check(args: argparse.Namespace) -> int:
    source = external_source_store(args).get(args.source_id)
    metadata, items, complete = InternetArchiveProvider().inspect(source, page_size=args.page_size)
    check_id = sha256(f"{source.id}:{metadata}".encode()).hexdigest()[:16]
    snapshot = create_snapshot(source.id, source.provider_type, check_id, metadata, items)
    SnapshotStore(Path(args.metadata_root)).save(snapshot)
    ExternalStorage(Path(args.metadata_root)).put("external-checks", check_id, {"id": check_id, "source_id": source.id, "status": "completed" if complete else "running", "snapshot_id": snapshot.id, "item_count": len(items)})
    print(json.dumps(asdict(snapshot), indent=2, sort_keys=True) if args.json else snapshot.id)
    return 0


def command_external_source_resume(args: argparse.Namespace) -> int:
    checks = InspectionStore(Path(args.metadata_root)); check = checks.load(args.check_id)
    source = external_source_store(args).get(check.source_id)
    result = inspect_resumable(source, InternetArchiveProvider(), checks, check.id, page_size=check.page_size)
    print(json.dumps(asdict(result), indent=2, sort_keys=True) if args.json else f"{result.id}: {result.status}")
    return 0 if result.status == "completed" else 2


def command_external_source_cancel(args: argparse.Namespace) -> int:
    checks = InspectionStore(Path(args.metadata_root)); check = checks.load(args.check_id)
    if check.status in {"completed", "cancelled"}: raise ValueError("inspection is not cancellable")
    result = checks.update(check, status="cancelled", resumable=False, final_result=args.reason, errors=tuple((*check.errors, args.reason)))
    print(result.id)
    return 0


def command_external_snapshot_list(args: argparse.Namespace) -> int:
    snapshots = SnapshotStore(Path(args.metadata_root)).list(args.source_id)
    print(json.dumps(list(snapshots), indent=2, sort_keys=True))
    return 0


def command_external_snapshot_show(args: argparse.Namespace) -> int:
    source = external_source_store(args).get(args.source_id)
    print(json.dumps(SnapshotStore(Path(args.metadata_root)).get(args.snapshot_id, source.id), indent=2, sort_keys=True))
    return 0


def command_external_source_history(args: argparse.Namespace) -> int:
    from preservation.external.checks import InspectionStore
    print(json.dumps([asdict(item) for item in InspectionStore(Path(args.metadata_root)).list(args.source_id)], indent=2, sort_keys=True))
    return 0


def command_external_diff(args: argparse.Namespace) -> int:
    storage = ExternalStorage(Path(args.metadata_root))
    def load(snapshot_id: str):
        for source in external_source_store(args).list():
            for raw in SnapshotStore(Path(args.metadata_root)).list(source.id):
                if raw.get("id") == snapshot_id:
                    from preservation.external.models import ExternalItem, ExternalFile, ExternalSnapshot
                    items = tuple(ExternalItem(**{**item, "subjects": tuple(item.get("subjects", ())), "collections": tuple(item.get("collections", ())), "files": tuple(ExternalFile(**file) for file in item.get("files", ()))}) for item in raw["items"])
                    return ExternalSnapshot(**{**raw, "items": items, "warnings": tuple(raw.get("warnings", ()))})
        raise ValueError(f"snapshot not found: {snapshot_id}")
    print(json.dumps(diff_snapshots(load(args.old_snapshot_id), load(args.new_snapshot_id)), indent=2, sort_keys=True))
    return 0


def command_mirror_plan_create(args: argparse.Namespace) -> int:
    source = external_source_store(args).get(args.source_id)
    raw = SnapshotStore(Path(args.metadata_root)).get(args.snapshot_id, source.id)
    from preservation.external.models import ExternalItem, ExternalFile, ExternalSnapshot
    items = tuple(ExternalItem(**{**item, "subjects": tuple(item.get("subjects", ())), "collections": tuple(item.get("collections", ())), "files": tuple(ExternalFile(**file) for file in item.get("files", ()))}) for item in raw["items"])
    snapshot = ExternalSnapshot(**{**raw, "items": items, "warnings": tuple(raw.get("warnings", ()))})
    plan = create_mirror_plan(source.id, snapshot, args.policy)
    MirrorPlanStore(Path(args.metadata_root)).save(plan)
    print(plan.id)
    return 0


def command_mirror_plan_show(args: argparse.Namespace) -> int:
    print(json.dumps(MirrorPlanStore(Path(args.metadata_root)).get(args.plan_id), indent=2, sort_keys=True))
    return 0


def _load_mirror_plan_snapshot(args):
    raw = MirrorPlanStore(Path(args.metadata_root)).get(args.plan_id)
    source = external_source_store(args).get(raw["source_id"])
    snap = SnapshotStore(Path(args.metadata_root)).get(raw["snapshot_id"], source.id)
    from preservation.external.models import ExternalItem, ExternalFile, ExternalSnapshot, MirrorPlan
    items = tuple(ExternalItem(**{**item, "subjects": tuple(item.get("subjects", ())), "collections": tuple(item.get("collections", ())), "files": tuple(ExternalFile(**file) for file in item.get("files", ()))}) for item in snap["items"])
    return MirrorPlan(**{**raw, "selected_files": tuple(raw.get("selected_files", ())), "excluded_files": tuple(raw.get("excluded_files", ())), "warnings": tuple(raw.get("warnings", ())), "blocking_issues": tuple(raw.get("blocking_issues", ())), "approval_history": tuple(raw.get("approval_history", ())), "cancellation_history": tuple(raw.get("cancellation_history", ())) }), ExternalSnapshot(**{**snap, "items": items, "warnings": tuple(snap.get("warnings", ()))})


def command_mirror_plan_validate(args: argparse.Namespace) -> int:
    plan, snapshot = _load_mirror_plan_snapshot(args); issues = validate_mirror_plan(plan, snapshot)
    print(json.dumps({"plan_id": plan.id, "valid": not issues, "issues": issues}, indent=2, sort_keys=True)); return 0 if not issues else 1


def command_mirror_plan_review(args: argparse.Namespace) -> int:
    plan, _ = _load_mirror_plan_snapshot(args); result = review_mirror_plan(plan)
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


def command_mirror_plan_approve(args: argparse.Namespace) -> int:
    plan, snapshot = _load_mirror_plan_snapshot(args); issues = validate_mirror_plan(plan, snapshot)
    if issues: raise ValueError("mirror plan validation failed: " + "; ".join(issues))
    from dataclasses import replace
    updated = replace(plan, status="approved", approval_history=tuple((*plan.approval_history, args.note or "approved")))
    MirrorPlanStore(Path(args.metadata_root)).save(updated); print(updated.id); return 0


def command_mirror_plan_cancel(args: argparse.Namespace) -> int:
    plan_raw = MirrorPlanStore(Path(args.metadata_root)).get(args.plan_id)
    if plan_raw.get("status") in {"executing", "completed", "cancelled"}: raise ValueError("mirror plan is not cancellable")
    plan, _ = _load_mirror_plan_snapshot(args)
    from dataclasses import replace
    updated = replace(plan, status="cancelled", cancellation_history=tuple((*plan.cancellation_history, args.reason)))
    MirrorPlanStore(Path(args.metadata_root)).save(updated); print(updated.id); return 0


def command_mirror_plan_preview(args: argparse.Namespace) -> int:
    plan, _ = _load_mirror_plan_snapshot(args)
    preview = [{"source_id": plan.source_id, "item": item.get("item"), "filename": item.get("filename"), "metadata_locator": item.get("locator"), "proposed_content_locator": item.get("locator"), "proposed_staging_path": f"/srv/amigalab/staging/external/{plan.id}/{item.get('filename')}", "proposed_media_path": f"/srv/amigalab/media/{plan.target_category}/{plan.id}/{item.get('filename')}", "size": item.get("size"), "md5": item.get("md5"), "sha1": item.get("sha1"), "future_import_mode": "media-only"} for item in plan.selected_files]
    print(json.dumps(preview, indent=2, sort_keys=True)); return 0


def command_mirror_execute(args: argparse.Namespace) -> int:
    plan, _ = _load_mirror_plan_snapshot(args); source = external_source_store(args).get(plan.source_id)
    if not args.yes: print(json.dumps({"plan_id": plan.id, "requires_confirmation": True}, indent=2)); return 1
    execution = execute_mirror(plan, source, MirrorExecutionStore(Path(args.metadata_root)), Path(args.staging_root), Path(args.media_root), yes=True)
    print(json.dumps(asdict(execution), indent=2, sort_keys=True) if args.json else execution.id); return 0 if execution.state == "completed" else 2


def command_mirror_status(args: argparse.Namespace) -> int:
    execution = MirrorExecutionStore(Path(args.metadata_root)).load_execution(args.execution_id)
    print(json.dumps(asdict(execution), indent=2, sort_keys=True) if args.json else f"{execution.id}: {execution.state}"); return 0


def command_mirror_resume(args: argparse.Namespace) -> int:
    store = MirrorExecutionStore(Path(args.metadata_root)); execution = store.load_execution(args.execution_id)
    plan, _ = _load_mirror_plan_snapshot(argparse.Namespace(metadata_root=args.metadata_root, plan_id=execution.plan_id))
    source = external_source_store(args).get(execution.source_id)
    if not args.yes: print(json.dumps({"execution_id": execution.id, "requires_confirmation": True}, indent=2)); return 1
    result = resume_mirror(execution, plan, source, store, Path(args.staging_root), Path(args.media_root), yes=True)
    print(json.dumps(asdict(result), indent=2, sort_keys=True) if args.json else result.id); return 0 if result.state == "completed" else 2


def command_mirror_report(args: argparse.Namespace) -> int:
    execution = MirrorExecutionStore(Path(args.metadata_root)).load_execution(args.execution_id)
    entries = MirrorExecutionStore(Path(args.metadata_root)).list_entries(execution.id)
    report = {"execution": asdict(execution), "entries": [asdict(entry) for entry in entries], "completed": len(execution.completed_entries), "reused": len(execution.reused_entries), "failed": len(execution.failed_entries)}
    print(json.dumps(report, indent=2, sort_keys=True)); return 0


def command_mirror_cancel(args: argparse.Namespace) -> int:
    store = MirrorExecutionStore(Path(args.metadata_root)); execution = store.load_execution(args.execution_id)
    if execution.state in {"completed", "cancelled"}: raise ValueError("execution is not cancellable")
    from dataclasses import replace
    updated = replace(execution, state="cancelled", resumable=False, final_result=args.reason, latest_error=args.reason, updated_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
    store.save_execution(updated); print(updated.id); return 0


def _find_acquisition(args, media_id):
    store = MirrorExecutionStore(Path(args.metadata_root))
    for raw in store.storage.list("mirror-acquisition-entries"):
        if raw.get("id") == media_id or raw.get("final_path", "").endswith(media_id):
            return store.load_entry(raw["id"]), store.load_execution(raw["execution_id"])
    raise ValueError(f"acquired media not found: {media_id}")


def command_media_analysis_create(args: argparse.Namespace) -> int:
    entry, execution = _find_acquisition(args, args.media_id)
    source = external_source_store(args).get(execution.source_id)
    analysis = analyze_media(args.media_id, entry, execution, source, execution.plan_id, execution.snapshot_id, media_root=Path(args.media_root))
    MediaAnalysisStore(Path(args.metadata_root)).save(analysis)
    print(json.dumps(asdict(analysis), indent=2, sort_keys=True) if args.json else analysis.id); return 0


def command_media_analysis_show(args: argparse.Namespace) -> int:
    print(json.dumps(asdict(MediaAnalysisStore(Path(args.metadata_root)).get(args.analysis_id)), indent=2, sort_keys=True)); return 0


def command_media_analysis_list(args: argparse.Namespace) -> int:
    values = [asdict(item) for item in MediaAnalysisStore(Path(args.metadata_root)).list()]
    print(json.dumps(values, indent=2, sort_keys=True)); return 0


def command_media_analysis_validate(args: argparse.Namespace) -> int:
    analysis = MediaAnalysisStore(Path(args.metadata_root)).get(args.analysis_id)
    path = Path(analysis.local_media_path)
    issues = []
    if not path.is_file(): issues.append("media is missing")
    elif local_hashes(path)[0] != analysis.local_media_hashes: issues.append("media hash changed")
    if analysis.blocking_findings: issues.extend(analysis.blocking_findings)
    print(json.dumps({"analysis_id": analysis.id, "valid": not issues, "issues": issues}, indent=2, sort_keys=True)); return 0 if not issues else 1


def command_media_analysis_report(args: argparse.Namespace) -> int:
    analysis = MediaAnalysisStore(Path(args.metadata_root)).get(args.analysis_id)
    report = {"analysis_id": analysis.id, "media_id": analysis.media_id, "container_type": analysis.container_type, "member_count": len(analysis.members), "total_member_bytes": sum(member.size for member in analysis.members), "candidate_collections": analysis.candidate_collections, "recommended_import_mode": analysis.recommended_import_mode, "sidecar_count": len(analysis.sidecar_groups), "unsafe_entries": analysis.unsafe_entries, "rom_candidates": analysis.rom_candidates, "workbench_candidates": analysis.workbench_candidates, "warnings": analysis.warnings, "blocking_findings": analysis.blocking_findings}
    print(json.dumps(report, indent=2, sort_keys=True)); return 0


def command_import_plan_from_media(args: argparse.Namespace) -> int:
    analysis = MediaAnalysisStore(Path(args.metadata_root)).get(args.analysis_id)
    plan = generate_import_plan(analysis, policy=args.policy, collection=args.collection)
    PlanStore(Path(args.metadata_root)).save(plan); save_link(Path(args.metadata_root), plan, analysis)
    print(plan.id); return 0


def command_media_trace(args: argparse.Namespace) -> int:
    result = enriched_media_trace(args.media_id, Path(args.metadata_root))
    try:
        entry, execution = _find_acquisition(args, args.media_id)
        result.update({"source_id": execution.source_id, "snapshot_id": execution.snapshot_id,
                       "mirror_plan_id": execution.plan_id, "mirror_execution_id": execution.id,
                       "acquisition_entry_id": entry.id})
    except (ValueError, OSError):
        result.setdefault("missing", []).append("acquisition")
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


def command_aminet_verify(args: argparse.Namespace) -> int:
    root = Path(args.archive_root) / args.collection
    report = verify_collection(args.collection, root, Path(args.metadata_root), args.policy)
    if getattr(args, "write", False):
        VerificationReportStore(Path(args.metadata_root)).save(report)
    print(json.dumps(asdict(report), indent=2, sort_keys=True) if getattr(args, "json", False) else f"{report.result}: {len(report.successful_files)} verified, {len(report.blocking_findings)} blocking")
    return 0 if report.result == "success" else 1


def command_verification_report_create(args: argparse.Namespace) -> int:
    report = verify_collection(args.collection, Path(args.archive_root) / args.collection, Path(args.metadata_root), args.policy)
    VerificationReportStore(Path(args.metadata_root)).save(report)
    print(json.dumps(asdict(report), indent=2, sort_keys=True) if args.json else report.id)
    return 0 if report.result == "success" else 1


def command_verification_report_show(args: argparse.Namespace) -> int:
    report = VerificationReportStore(Path(args.metadata_root)).get(args.report_id)
    if report is None:
        raise ValueError(f"unknown verification report: {args.report_id}")
    print(json.dumps(report, indent=2, sort_keys=True)); return 0


def command_verification_report_list(args: argparse.Namespace) -> int:
    print(json.dumps(VerificationReportStore(Path(args.metadata_root)).list(), indent=2, sort_keys=True)); return 0


def command_collection_reconcile(args: argparse.Namespace) -> int:
    result = reconciliation(args.collection, Path(args.archive_root) / args.collection, Path(args.metadata_root))
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if not result.get("blocking") else 1


def command_collection_repair_plan(args: argparse.Namespace) -> int:
    result = repair_plan(args.collection, Path(args.archive_root) / args.collection, Path(args.metadata_root))
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


def command_object_trace(args: argparse.Namespace) -> int:
    result = object_trace(args.object_id, Path(args.metadata_root))
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result.get("found") else 1


def command_file_trace(args: argparse.Namespace) -> int:
    result = file_trace(args.file_id, Path(args.metadata_root))
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result.get("found") else 1


def command_relationship_backfill(args: argparse.Namespace) -> int:
    result = create_relationship_backfill_plan(args.collection, Path(args.archive_root) / args.collection, Path(args.metadata_root))
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if not result.get("blocking_findings") else 1


def _operations_config() -> dict:
    # Installation defaults are deliberately disabled; deployments may wrap the
    # CLI with a validated configuration provider without changing this command.
    return {"enabled": os.environ.get("AMIGALAB_OPERATIONS_ENABLED", "false").lower() == "true", "operations": {}}


def command_operations_preview(args: argparse.Namespace) -> int:
    print(json.dumps(operations_preview(_operations_config(), Path(args.metadata_root)), indent=2, sort_keys=True)); return 0


def command_operations_status(args: argparse.Namespace) -> int:
    store = OperationsStore(Path(args.metadata_root)); runs = list(store.list_runs())
    result = {"enabled": _operations_config()["enabled"], "run_count": len(runs), "last_run": runs[-1] if runs else None,
              "active_locks": [str(p) for p in (Path(args.metadata_root).parent / "run" / "locks").glob("amigalab-*.lock")],
              "pending_draft_mirror_plans": len([p for p in ExternalStorage(Path(args.metadata_root)).list("mirror-plans") if p.get("status") == "draft"]),
              "pending_import_plans": len([p for p in ExternalStorage(Path(args.metadata_root)).list("import-plans") if p.get("status") in {"draft", "ready", "approved"}])}
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


def command_operations_history(args: argparse.Namespace) -> int:
    print(json.dumps(list(OperationsStore(Path(args.metadata_root)).list_runs()), indent=2, sort_keys=True)); return 0


def command_operations_report(args: argparse.Namespace) -> int:
    run = OperationsStore(Path(args.metadata_root)).get_run(args.run_id)
    if run is None: raise ValueError(f"unknown operations run: {args.run_id}")
    print(json.dumps(run, indent=2, sort_keys=True)); return 0


def _run_record(args, operation: str, target: str) -> OperationsRun:
    run_id = __import__('hashlib').sha256(f"{operation}:{target}:{now()}".encode()).hexdigest()
    run = OperationsRun(run_id, operation, getattr(args, "trigger", "manual"), target, now(), now(), state="running")
    store = OperationsStore(Path(args.metadata_root)); store.save_run(run); store.event(run.id, "run-start", operation_name=operation, target=target)
    return run


def command_scheduled_verify(args: argparse.Namespace) -> int:
    run = _run_record(args, "verification", args.collection); store = OperationsStore(Path(args.metadata_root))
    try:
        with OperationsLock(Path(args.metadata_root).parent, f"verify-{args.collection}"):
            report = verify_collection(args.collection, Path(args.archive_root) / args.collection, Path(args.metadata_root), args.policy)
            report_id = VerificationReportStore(Path(args.metadata_root)).save(report).stem
            final = __import__('dataclasses').replace(run, state="completed" if report.result == "success" else "completed-with-warnings", result=report.result, completed_at=now(), updated_at=now(), created_record_ids=(report_id,))
            store.save_run(final)
            print(json.dumps({"run": asdict(final), "report": asdict(report)}, indent=2, sort_keys=True)); return 0 if report.result == "success" else 1
    except RuntimeError as error:
        final = __import__('dataclasses').replace(run, state="blocked", result=str(error), completed_at=now(), updated_at=now(), errors=(str(error),)); store.save_run(final); raise


def command_scheduled_source_check(args: argparse.Namespace) -> int:
    run = _run_record(args, "source-check", args.source_id); store = OperationsStore(Path(args.metadata_root))
    try:
        with OperationsLock(Path(args.metadata_root).parent, f"external-source-{args.source_id}"):
            source_args = dict(vars(args)); source_args["json"] = True
            result = command_external_source_check(argparse.Namespace(**source_args))
            final = __import__('dataclasses').replace(run, state="completed", result="success", completed_at=now(), updated_at=now())
            store.save_run(final); return result
    except Exception as error:
        final = __import__('dataclasses').replace(run, state="failed", result="failed", completed_at=now(), updated_at=now(), errors=(str(error),)); store.save_run(final); raise


def command_scheduled_reconcile(args: argparse.Namespace) -> int:
    run = _run_record(args, "reconciliation", args.collection); store = OperationsStore(Path(args.metadata_root))
    result = reconciliation(args.collection, Path(args.archive_root) / args.collection, Path(args.metadata_root))
    final = __import__('dataclasses').replace(run, state="completed", result="success" if not result.get("blocking") else "warnings", completed_at=now(), updated_at=now())
    store.save_run(final); print(json.dumps({"run": asdict(final), "reconciliation": result}, indent=2, sort_keys=True)); return 0 if not result.get("blocking") else 1


def command_retention_plan(args: argparse.Namespace) -> int:
    plan = retention_plan(Path(args.metadata_root)); ExternalStorage(Path(args.metadata_root)).put("retention-plans", plan["id"], plan); print(json.dumps(plan, indent=2, sort_keys=True)); return 0


def command_retention_execute(args: argparse.Namespace) -> int:
    if not args.yes: raise PermissionError("retention execution requires explicit confirmation: pass --yes")
    plan = ExternalStorage(Path(args.metadata_root)).get("retention-plans", args.plan_id)
    if plan.get("blocking_findings"): raise ValueError("retention plan is blocked")
    run = _run_record(args, "retention", args.plan_id)
    removed = []
    cache_root = (Path(args.metadata_root).parent / "cache" / "external-providers").resolve()
    for candidate in plan.get("candidates", []):
        path = Path(candidate["path"])
        try:
            safe = path.resolve().is_relative_to(cache_root)
        except OSError:
            safe = False
        if safe and path.is_file() and not path.is_symlink():
            path.unlink()
            removed.append(str(path))
    final = __import__('dataclasses').replace(run, state="completed", result="success", completed_at=now(), updated_at=now(), created_record_ids=tuple(removed))
    OperationsStore(Path(args.metadata_root)).save_run(final); print(json.dumps(asdict(final), indent=2, sort_keys=True)); return 0


def command_retention_report(args: argparse.Namespace) -> int:
    return command_operations_report(argparse.Namespace(metadata_root=args.metadata_root, run_id=args.execution_id))


def _catalog_db(args):
    return Path(getattr(args, "catalog_database", "") or (Path(args.metadata_root) / "catalog" / "catalog.db"))


def command_catalog_build(args):
    result = build_catalog(Path(args.metadata_root), Path(args.archive_root), _catalog_db(args), args.max_text_bytes)
    build_id = sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    ExternalStorage(Path(args.metadata_root)).put("catalog-builds", build_id, {"id": build_id, **result, "database": str(_catalog_db(args)), "completed_at": now(), "schema_version": 1})
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


def command_catalog_update(args):
    return command_catalog_build(args)


def command_catalog_verify(args):
    result = verify_catalog(_catalog_db(args)); print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result.get("valid") else 1


def command_catalog_search(args):
    rows = CatalogIndex(_catalog_db(args)).search(args.query, collection=args.collection, entity_type=args.type, extension=args.extension, path_prefix=args.path_prefix, license_profile=args.license, verification=args.verification, source=args.source, limit=args.limit, offset=args.offset)
    values = []
    for raw, rank in rows:
        item = json.loads(raw); item["rank"] = rank; values.append(item)
    print(json.dumps(values, indent=2, sort_keys=True) if args.json else "\n".join(f"{v['id']}\t{v.get('title','')}\t{v.get('relative_path','')}" for v in values)); return 0


def command_catalog_show(args):
    value = CatalogIndex(_catalog_db(args)).show(args.document_id)
    if value is None: raise ValueError(f"unknown catalog document: {args.document_id}")
    print(json.dumps(value, indent=2, sort_keys=True)); return 0


def command_catalog_stats(args):
    print(json.dumps(CatalogIndex(_catalog_db(args)).stats(), indent=2, sort_keys=True)); return 0


def command_catalog_history(args):
    print(json.dumps(list(ExternalStorage(Path(args.metadata_root)).list("catalog-builds")), indent=2, sort_keys=True)); return 0


def command_web_config_check(args):
    config = WebConfig(_catalog_db(args), args.bind, args.port, enabled=args.enabled)
    config.validate()
    if config.bind != "127.0.0.1" and not config.enabled:
        raise ValueError("remote AmigaLab web binding requires --enabled acknowledgement")
    print(json.dumps({"valid": True, "bind": config.bind, "port": config.port, "database": str(config.database), "enabled": config.enabled}, sort_keys=True)); return 0


def command_web_status(args):
    config = WebConfig(_catalog_db(args), args.bind, args.port)
    health = verify_catalog(config.database) if config.database.is_file() else {"valid": False, "error": "catalog unavailable"}
    print(json.dumps({"configured": config.enabled, "bind": config.bind, "port": config.port, "catalog": health}, indent=2, sort_keys=True)); return 0


def command_web_run(args):
    run_web(WebConfig(_catalog_db(args), args.bind, args.port, enabled=args.enabled))
    return 0


def _meili(args):
    from os import environ
    return MeiliClient(args.endpoint, args.index, args.timeout, environ.get("AMIGALAB_MEILISEARCH_API_KEY", ""))


def command_meilisearch_sync(args):
    client = _meili(args); documents = build_documents(Path(args.metadata_root), Path(args.archive_root), args.max_text_bytes)
    result = client.sync(list(documents), args.batch_size)
    report = {"id": sha256(json.dumps({"index": args.index, "count": len(documents), "result": result.status}, sort_keys=True).encode()).hexdigest(), "index": args.index, "documents_considered": len(documents), "documents_added": result.added, "documents_updated": result.updated, "errors": result.errors, "status": result.status}
    ExternalStorage(Path(args.metadata_root)).put("catalog/meilisearch-syncs", report["id"], report)
    print(json.dumps(report, indent=2, sort_keys=True)); return 0 if result.status == "success" else 3


def command_meilisearch_status(args):
    try: result = _meili(args).health(); output = {"configured": True, "healthy": True, "health": result}
    except (OSError, ValueError) as error: output = {"configured": True, "healthy": False, "error": str(error)}
    print(json.dumps(output, indent=2, sort_keys=True)); return 0 if output["healthy"] else 1


def command_meilisearch_verify(args):
    return command_meilisearch_status(args)


def command_meilisearch_clear(args):
    if not args.yes: raise PermissionError("Meilisearch clear requires --yes")
    client = _meili(args); client._request("DELETE", f"/indexes/{client.index}"); print(client.index); return 0


def command_web_verify(args):
    config = WebConfig(_catalog_db(args), args.bind, args.port, enabled=args.enabled); config.validate()
    result = verify_catalog(config.database) if config.database.is_file() else {"valid": False, "error": "catalog unavailable"}
    print(json.dumps({"config_valid": True, "catalog": result, "read_only": True}, indent=2, sort_keys=True)); return 0 if result.get("valid") else 1


def parser() -> argparse.ArgumentParser:
    default_root = os.environ.get("AMIGALAB_STORAGE_ROOT", "/srv/amigalab")
    command_parser = argparse.ArgumentParser(description=__doc__)
    command_parser.add_argument("--version", action="version", version=f"AmigaLab {__version__}")
    command_parser.add_argument("--archive-root", default=default_root)
    command_parser.add_argument("--metadata-root", default=f"{default_root}/metadata")
    command_parser.add_argument("--staging-root", default=f"{default_root}/staging")
    commands = command_parser.add_subparsers(dest="command", required=True)

    source_add = commands.add_parser("source-add", help="register a preservation source")
    source_add.add_argument("--id", required=True)
    source_add.add_argument("--name", required=True)
    source_add.add_argument("--kind", required=True, choices=sorted(SUPPORTED_SOURCE_KINDS))
    source_add.add_argument("--location", required=True)
    source_add.add_argument("--license-profile", default="unknown")
    source_add.add_argument("--media-classification", default="unknown")
    source_add.add_argument("--notes", default="")
    source_add.set_defaults(handler=command_source_add)

    scan_command = commands.add_parser("scan", help="read-only source preview")
    scan_command.add_argument("location")
    scan_command.add_argument("--collection", help="collection name (defaults to source directory name)")
    scan_command.set_defaults(handler=command_scan)

    import_command = commands.add_parser("import", help="copy-only import after confirmation")
    import_command.add_argument("location")
    import_command.add_argument("--collection", required=True)
    import_command.add_argument("--source", required=True)
    import_command.add_argument("--yes", action="store_true", help="confirm the copy-only import")
    import_command.set_defaults(handler=command_import)

    verify_command = commands.add_parser("verify", help="verify objects registered for a collection")
    verify_command.add_argument("collection_name", nargs="?")
    verify_command.add_argument("--collection", default="aminet")
    verify_command.add_argument("--algorithm", default="sha256", choices=("md5", "sha1", "sha256", "sha512"))
    verify_command.set_defaults(handler=command_verify)
    aminet_verify = commands.add_parser("aminet-verify", help="read-only Aminet collection verification")
    aminet_verify.add_argument("--collection", default="aminet"); aminet_verify.add_argument("--policy", choices=("metadata-only", "sha256", "full-hashes"), default="full-hashes"); aminet_verify.add_argument("--json", action="store_true"); aminet_verify.add_argument("--write", action="store_true"); aminet_verify.set_defaults(handler=command_aminet_verify)
    report_create = commands.add_parser("verification-report-create"); report_create.add_argument("collection"); report_create.add_argument("--policy", choices=("metadata-only", "sha256", "full-hashes"), default="full-hashes"); report_create.add_argument("--json", action="store_true"); report_create.set_defaults(handler=command_verification_report_create)
    report_show = commands.add_parser("verification-report-show"); report_show.add_argument("report_id"); report_show.add_argument("--json", action="store_true"); report_show.set_defaults(handler=command_verification_report_show)
    report_list = commands.add_parser("verification-report-list"); report_list.add_argument("--json", action="store_true"); report_list.set_defaults(handler=command_verification_report_list)
    collection_reconcile = commands.add_parser("collection-reconcile"); collection_reconcile.add_argument("collection"); collection_reconcile.set_defaults(handler=command_collection_reconcile)
    repair = commands.add_parser("collection-repair-plan"); repair.add_argument("collection"); repair.set_defaults(handler=command_collection_repair_plan)
    object_trace_cmd = commands.add_parser("object-trace"); object_trace_cmd.add_argument("object_id"); object_trace_cmd.add_argument("--json", action="store_true"); object_trace_cmd.set_defaults(handler=command_object_trace)
    file_trace_cmd = commands.add_parser("file-trace"); file_trace_cmd.add_argument("file_id"); file_trace_cmd.add_argument("--json", action="store_true"); file_trace_cmd.set_defaults(handler=command_file_trace)
    backfill = commands.add_parser("relationship-backfill"); backfill.add_argument("collection"); backfill.add_argument("--plan-only", action="store_true", default=True); backfill.set_defaults(handler=command_relationship_backfill)
    operations_preview_cmd = commands.add_parser("operations-preview"); operations_preview_cmd.set_defaults(handler=command_operations_preview)
    operations_status_cmd = commands.add_parser("operations-status"); operations_status_cmd.add_argument("--json", action="store_true"); operations_status_cmd.set_defaults(handler=command_operations_status)
    operations_history_cmd = commands.add_parser("operations-history"); operations_history_cmd.add_argument("--json", action="store_true"); operations_history_cmd.set_defaults(handler=command_operations_history)
    operations_report_cmd = commands.add_parser("operations-report"); operations_report_cmd.add_argument("run_id"); operations_report_cmd.set_defaults(handler=command_operations_report)
    scheduled_source = commands.add_parser("scheduled-source-check"); scheduled_source.add_argument("source_id"); scheduled_source.add_argument("--page-size", type=int, default=50); scheduled_source.add_argument("--json", action="store_true"); scheduled_source.set_defaults(handler=command_scheduled_source_check)
    scheduled_verify = commands.add_parser("scheduled-verify"); scheduled_verify.add_argument("collection"); scheduled_verify.add_argument("--policy", choices=("metadata-only", "sha256", "full-hashes"), default="sha256"); scheduled_verify.set_defaults(handler=command_scheduled_verify)
    scheduled_reconcile = commands.add_parser("scheduled-reconcile"); scheduled_reconcile.add_argument("collection"); scheduled_reconcile.set_defaults(handler=command_scheduled_reconcile)
    retention_plan_cmd = commands.add_parser("retention-plan"); retention_plan_cmd.set_defaults(handler=command_retention_plan)
    retention_execute_cmd = commands.add_parser("retention-execute"); retention_execute_cmd.add_argument("plan_id"); retention_execute_cmd.add_argument("--yes", action="store_true"); retention_execute_cmd.set_defaults(handler=command_retention_execute)
    retention_report_cmd = commands.add_parser("retention-report"); retention_report_cmd.add_argument("execution_id"); retention_report_cmd.set_defaults(handler=command_retention_report)
    catalog_build_cmd = commands.add_parser("catalog-build"); catalog_build_cmd.add_argument("--catalog-database"); catalog_build_cmd.add_argument("--max-text-bytes", type=int, default=1048576); catalog_build_cmd.set_defaults(handler=command_catalog_build)
    catalog_update_cmd = commands.add_parser("catalog-update"); catalog_update_cmd.add_argument("--catalog-database"); catalog_update_cmd.add_argument("--max-text-bytes", type=int, default=1048576); catalog_update_cmd.set_defaults(handler=command_catalog_update)
    catalog_verify_cmd = commands.add_parser("catalog-verify"); catalog_verify_cmd.add_argument("--catalog-database"); catalog_verify_cmd.set_defaults(handler=command_catalog_verify)
    catalog_search_cmd = commands.add_parser("search"); catalog_search_cmd.add_argument("query"); catalog_search_cmd.add_argument("--catalog-database"); catalog_search_cmd.add_argument("--collection"); catalog_search_cmd.add_argument("--type"); catalog_search_cmd.add_argument("--extension"); catalog_search_cmd.add_argument("--path-prefix"); catalog_search_cmd.add_argument("--license"); catalog_search_cmd.add_argument("--verification"); catalog_search_cmd.add_argument("--source"); catalog_search_cmd.add_argument("--limit", type=int, default=20); catalog_search_cmd.add_argument("--offset", type=int, default=0); catalog_search_cmd.add_argument("--json", action="store_true"); catalog_search_cmd.set_defaults(handler=command_catalog_search)
    catalog_show_cmd = commands.add_parser("catalog-show"); catalog_show_cmd.add_argument("document_id"); catalog_show_cmd.add_argument("--catalog-database"); catalog_show_cmd.set_defaults(handler=command_catalog_show)
    catalog_stats_cmd = commands.add_parser("catalog-stats"); catalog_stats_cmd.add_argument("--catalog-database"); catalog_stats_cmd.set_defaults(handler=command_catalog_stats)
    catalog_history_cmd = commands.add_parser("catalog-build-history"); catalog_history_cmd.set_defaults(handler=command_catalog_history)
    web_run_cmd = commands.add_parser("web-run"); web_run_cmd.add_argument("--bind", default="127.0.0.1"); web_run_cmd.add_argument("--port", type=int, default=8787); web_run_cmd.add_argument("--enabled", action="store_true"); web_run_cmd.set_defaults(handler=command_web_run)
    web_status_cmd = commands.add_parser("web-status"); web_status_cmd.add_argument("--bind", default="127.0.0.1"); web_status_cmd.add_argument("--port", type=int, default=8787); web_status_cmd.set_defaults(handler=command_web_status)
    web_config_cmd = commands.add_parser("web-config-check"); web_config_cmd.add_argument("--bind", default="127.0.0.1"); web_config_cmd.add_argument("--port", type=int, default=8787); web_config_cmd.add_argument("--enabled", action="store_true"); web_config_cmd.set_defaults(handler=command_web_config_check)
    web_verify_cmd = commands.add_parser("web-verify"); web_verify_cmd.add_argument("--bind", default="127.0.0.1"); web_verify_cmd.add_argument("--port", type=int, default=8787); web_verify_cmd.add_argument("--enabled", action="store_true"); web_verify_cmd.set_defaults(handler=command_web_verify)
    meili_sync = commands.add_parser("meilisearch-sync"); meili_sync.add_argument("--endpoint", default="http://127.0.0.1:7700"); meili_sync.add_argument("--index", default="amigalab_catalog"); meili_sync.add_argument("--timeout", type=int, default=15); meili_sync.add_argument("--batch-size", type=int, default=500); meili_sync.add_argument("--max-text-bytes", type=int, default=1048576); meili_sync.set_defaults(handler=command_meilisearch_sync)
    meili_status = commands.add_parser("meilisearch-status"); meili_status.add_argument("--endpoint", default="http://127.0.0.1:7700"); meili_status.add_argument("--index", default="amigalab_catalog"); meili_status.add_argument("--timeout", type=int, default=15); meili_status.set_defaults(handler=command_meilisearch_status)
    meili_verify = commands.add_parser("meilisearch-verify"); meili_verify.add_argument("--endpoint", default="http://127.0.0.1:7700"); meili_verify.add_argument("--index", default="amigalab_catalog"); meili_verify.add_argument("--timeout", type=int, default=15); meili_verify.add_argument("--full", action="store_true"); meili_verify.set_defaults(handler=command_meilisearch_verify)
    meili_clear = commands.add_parser("meilisearch-clear"); meili_clear.add_argument("--endpoint", default="http://127.0.0.1:7700"); meili_clear.add_argument("--index", default="amigalab_catalog"); meili_clear.add_argument("--timeout", type=int, default=15); meili_clear.add_argument("--yes", action="store_true"); meili_clear.set_defaults(handler=command_meilisearch_clear)

    media_scan = commands.add_parser("media-scan", help="read-only adapter inspection")
    media_scan.add_argument("location")
    media_scan.add_argument("--kind")
    media_scan.set_defaults(handler=command_media_scan)

    media_import = commands.add_parser("media-import", help="register original media only")
    media_import.add_argument("location")
    media_import.add_argument("--source", required=True)
    media_import.add_argument("--title", required=True)
    media_import.add_argument("--license-profile", default="unknown")
    media_import.add_argument("--notes", default="")
    media_import.add_argument("--yes", action="store_true")
    media_import.add_argument("--media-root", default=f"{default_root}/media")
    media_import.set_defaults(handler=command_media_import)

    discover = commands.add_parser("discover", help="conservative ROM/media candidates")
    discover.add_argument("location")
    discover.set_defaults(handler=command_discover)

    status = commands.add_parser("transaction-status", help="show canonical transaction state")
    status.add_argument("transaction_id")
    status.set_defaults(handler=command_transaction_status)
    reconcile = commands.add_parser("transaction-reconcile", help="read-only canonical transaction reconciliation")
    reconcile.add_argument("transaction_id")
    reconcile.set_defaults(handler=command_transaction_reconcile)
    resume = commands.add_parser("transaction-resume", help="resume an unchanged source transaction")
    resume.add_argument("transaction_id")
    resume.add_argument("--yes", action="store_true")
    resume.add_argument("--plan-only", action="store_true")
    resume.set_defaults(handler=command_transaction_resume)
    conflicts = commands.add_parser("conflict-report", help="write structured path conflict JSON")
    conflicts.add_argument("location")
    conflicts.add_argument("--collection", required=True)
    conflicts.add_argument("--source", required=True)
    conflicts.set_defaults(handler=command_conflict_report)
    plan = commands.add_parser("plan-create", help="create canonical selective import plan")
    plan.add_argument("location")
    plan.add_argument("--source", required=True)
    plan.add_argument("--collection", required=True)
    plan.add_argument("--kind")
    plan.add_argument("--mode", choices=("media-only", "members-only", "media-and-members"), default="media-only")
    plan.add_argument("--path", dest="paths", action="append")
    plan.add_argument("--include", action="append")
    plan.add_argument("--exclude", action="append")
    plan.set_defaults(handler=command_plan_create)
    plan_show = commands.add_parser("plan-show")
    plan_show.add_argument("plan_id")
    plan_show.set_defaults(handler=command_plan_show)
    plan_approve = commands.add_parser("plan-approve")
    plan_approve.add_argument("plan_id")
    plan_approve.add_argument("--note", default="")
    plan_approve.set_defaults(handler=command_plan_approve)
    plan_validate = commands.add_parser("plan-validate")
    plan_validate.add_argument("plan_id")
    plan_validate.set_defaults(handler=command_plan_validate)
    plan_cancel = commands.add_parser("plan-cancel")
    plan_cancel.add_argument("plan_id")
    plan_cancel.add_argument("--reason", default="cancelled by operator")
    plan_cancel.set_defaults(handler=command_plan_cancel)
    plan_execute = commands.add_parser("plan-execute")
    plan_execute.add_argument("plan_id")
    plan_execute.add_argument("--yes", action="store_true")
    plan_execute.add_argument("--media-root", default=f"{default_root}/media")
    plan_execute.set_defaults(handler=command_plan_execute)
    conflict_list = commands.add_parser("conflict-list")
    conflict_list.add_argument("plan_id")
    conflict_list.set_defaults(handler=command_conflict_list)
    conflict_decide = commands.add_parser("conflict-decide")
    conflict_decide.add_argument("conflict_id")
    conflict_decide.add_argument("--plan-id", required=True)
    conflict_decide.add_argument("--action", required=True)
    conflict_decide.add_argument("--reason", default="operator decision")
    conflict_decide.set_defaults(handler=command_conflict_decide)
    recovery_plan = commands.add_parser("recovery-plan", help="generate deterministic recovery plan")
    recovery_plan.add_argument("transaction_id")
    recovery_plan.add_argument("--source-path")
    recovery_plan.add_argument("--write", action="store_true")
    recovery_plan.set_defaults(handler=command_recovery_plan)
    recovery_dry = commands.add_parser("recovery-dry-run", help="validate a recovery plan without mutation")
    recovery_dry.add_argument("plan_id")
    recovery_dry.add_argument("--write-report", action="store_true")
    recovery_dry.set_defaults(handler=command_recovery_dry_run)
    recovery_report = commands.add_parser("recovery-report", help="show a persisted recovery report")
    recovery_report.add_argument("report_id")
    recovery_report.set_defaults(handler=command_recovery_report)
    recovery_execute = commands.add_parser("recovery-execute", help="execute a persisted recovery plan")
    recovery_execute.add_argument("plan_id")
    recovery_execute.add_argument("--json", action="store_true")
    recovery_execute.set_defaults(handler=command_recovery_execute)
    recovery_resume = commands.add_parser("recovery-resume", help="resume a persisted recovery execution")
    recovery_resume.add_argument("plan_id")
    recovery_resume.add_argument("execution_id")
    recovery_resume.add_argument("--json", action="store_true")
    recovery_resume.set_defaults(handler=command_recovery_resume)
    external_add = commands.add_parser("external-source-add")
    external_add.add_argument("--id", required=True); external_add.add_argument("--name", required=True); external_add.add_argument("--description", default=""); external_add.add_argument("--locator", default="https://archive.org"); external_add.add_argument("--upstream-identifier", required=True); external_add.add_argument("--target", default="unknown"); external_add.add_argument("--platform-tag", action="append", default=[]); external_add.add_argument("--content-tag", action="append", default=[]); external_add.add_argument("--license-profile", default="unknown"); external_add.add_argument("--media-classification", default="unknown")
    external_add.set_defaults(handler=command_external_source_add)
    external_list = commands.add_parser("external-source-list"); external_list.add_argument("--json", action="store_true"); external_list.set_defaults(handler=command_external_source_list)
    external_show = commands.add_parser("external-source-show"); external_show.add_argument("source_id"); external_show.set_defaults(handler=command_external_source_show)
    external_check = commands.add_parser("external-source-check"); external_check.add_argument("source_id"); external_check.add_argument("--page-size", type=int, default=50); external_check.add_argument("--json", action="store_true"); external_check.set_defaults(handler=command_external_source_check)
    external_resume = commands.add_parser("external-source-resume"); external_resume.add_argument("check_id"); external_resume.add_argument("--json", action="store_true"); external_resume.set_defaults(handler=command_external_source_resume)
    external_cancel = commands.add_parser("external-source-cancel"); external_cancel.add_argument("check_id"); external_cancel.add_argument("--reason", default="cancelled by operator"); external_cancel.set_defaults(handler=command_external_source_cancel)
    snapshot_list = commands.add_parser("external-snapshot-list"); snapshot_list.add_argument("source_id"); snapshot_list.set_defaults(handler=command_external_snapshot_list)
    snapshot_show = commands.add_parser("external-snapshot-show"); snapshot_show.add_argument("source_id"); snapshot_show.add_argument("snapshot_id"); snapshot_show.set_defaults(handler=command_external_snapshot_show)
    source_history = commands.add_parser("external-source-history"); source_history.add_argument("source_id"); source_history.set_defaults(handler=command_external_source_history)
    external_diff = commands.add_parser("external-diff"); external_diff.add_argument("old_snapshot_id"); external_diff.add_argument("new_snapshot_id"); external_diff.set_defaults(handler=command_external_diff)
    mirror_create = commands.add_parser("mirror-plan-create"); mirror_create.add_argument("source_id"); mirror_create.add_argument("snapshot_id"); mirror_create.add_argument("--policy", default="original-media"); mirror_create.set_defaults(handler=command_mirror_plan_create)
    mirror_show = commands.add_parser("mirror-plan-show"); mirror_show.add_argument("plan_id"); mirror_show.set_defaults(handler=command_mirror_plan_show)
    mirror_validate = commands.add_parser("mirror-plan-validate"); mirror_validate.add_argument("plan_id"); mirror_validate.set_defaults(handler=command_mirror_plan_validate)
    mirror_review = commands.add_parser("mirror-plan-review"); mirror_review.add_argument("plan_id"); mirror_review.set_defaults(handler=command_mirror_plan_review)
    mirror_approve = commands.add_parser("mirror-plan-approve"); mirror_approve.add_argument("plan_id"); mirror_approve.add_argument("--note", default=""); mirror_approve.set_defaults(handler=command_mirror_plan_approve)
    mirror_cancel = commands.add_parser("mirror-plan-cancel"); mirror_cancel.add_argument("plan_id"); mirror_cancel.add_argument("--reason", default="cancelled by operator"); mirror_cancel.set_defaults(handler=command_mirror_plan_cancel)
    mirror_preview = commands.add_parser("mirror-plan-preview"); mirror_preview.add_argument("plan_id"); mirror_preview.set_defaults(handler=command_mirror_plan_preview)
    mirror_execute = commands.add_parser("mirror-execute"); mirror_execute.add_argument("plan_id"); mirror_execute.add_argument("--yes", action="store_true"); mirror_execute.add_argument("--json", action="store_true"); mirror_execute.add_argument("--media-root", default=f"{default_root}/media"); mirror_execute.set_defaults(handler=command_mirror_execute)
    mirror_status = commands.add_parser("mirror-status"); mirror_status.add_argument("execution_id"); mirror_status.add_argument("--json", action="store_true"); mirror_status.set_defaults(handler=command_mirror_status)
    mirror_resume = commands.add_parser("mirror-resume"); mirror_resume.add_argument("execution_id"); mirror_resume.add_argument("--yes", action="store_true"); mirror_resume.add_argument("--json", action="store_true"); mirror_resume.add_argument("--media-root", default=f"{default_root}/media"); mirror_resume.set_defaults(handler=command_mirror_resume)
    mirror_report = commands.add_parser("mirror-report"); mirror_report.add_argument("execution_id"); mirror_report.set_defaults(handler=command_mirror_report)
    mirror_cancel = commands.add_parser("mirror-cancel"); mirror_cancel.add_argument("execution_id"); mirror_cancel.add_argument("--reason", default="cancelled by operator"); mirror_cancel.set_defaults(handler=command_mirror_cancel)
    analysis_create = commands.add_parser("media-analysis-create"); analysis_create.add_argument("media_id"); analysis_create.add_argument("--media-root", default=f"{default_root}/media"); analysis_create.add_argument("--json", action="store_true"); analysis_create.set_defaults(handler=command_media_analysis_create)
    analysis_show = commands.add_parser("media-analysis-show"); analysis_show.add_argument("analysis_id"); analysis_show.set_defaults(handler=command_media_analysis_show)
    analysis_list = commands.add_parser("media-analysis-list"); analysis_list.set_defaults(handler=command_media_analysis_list)
    analysis_validate = commands.add_parser("media-analysis-validate"); analysis_validate.add_argument("analysis_id"); analysis_validate.set_defaults(handler=command_media_analysis_validate)
    analysis_report = commands.add_parser("media-analysis-report"); analysis_report.add_argument("analysis_id"); analysis_report.set_defaults(handler=command_media_analysis_report)
    import_from_media = commands.add_parser("import-plan-from-media"); import_from_media.add_argument("analysis_id"); import_from_media.add_argument("--policy", default="all-safe-members"); import_from_media.add_argument("--collection"); import_from_media.set_defaults(handler=command_import_plan_from_media)
    media_trace = commands.add_parser("media-trace"); media_trace.add_argument("media_id"); media_trace.add_argument("--json", action="store_true"); media_trace.set_defaults(handler=command_media_trace)
    return command_parser


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, PermissionError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
