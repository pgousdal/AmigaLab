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
from preservation.external.storage import ExternalStorage


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
    store = MetadataStore(metadata_root)
    failures = 0
    for object_ in store.list_objects():
        if object_.original_collection != args.collection:
            continue
        event = verify_object(object_, archive_root / args.collection, args.algorithm)
        store.save_verification(event)
        store.save_object(append_verification(object_, event))
        if not event.success:
            failures += 1
    print(f"Verified collection {args.collection}: {failures} failed object(s)")
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


def parser() -> argparse.ArgumentParser:
    default_root = os.environ.get("AMIGALAB_STORAGE_ROOT", "/srv/amigalab")
    command_parser = argparse.ArgumentParser(description=__doc__)
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
    verify_command.add_argument("--collection", required=True)
    verify_command.add_argument("--algorithm", default="sha256", choices=("md5", "sha1", "sha256", "sha512"))
    verify_command.set_defaults(handler=command_verify)

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
    snapshot_list = commands.add_parser("external-snapshot-list"); snapshot_list.add_argument("source_id"); snapshot_list.set_defaults(handler=command_external_snapshot_list)
    snapshot_show = commands.add_parser("external-snapshot-show"); snapshot_show.add_argument("source_id"); snapshot_show.add_argument("snapshot_id"); snapshot_show.set_defaults(handler=command_external_snapshot_show)
    source_history = commands.add_parser("external-source-history"); source_history.add_argument("source_id"); source_history.set_defaults(handler=command_external_source_history)
    external_diff = commands.add_parser("external-diff"); external_diff.add_argument("old_snapshot_id"); external_diff.add_argument("new_snapshot_id"); external_diff.set_defaults(handler=command_external_diff)
    mirror_create = commands.add_parser("mirror-plan-create"); mirror_create.add_argument("source_id"); mirror_create.add_argument("snapshot_id"); mirror_create.add_argument("--policy", default="original-media"); mirror_create.set_defaults(handler=command_mirror_plan_create)
    mirror_show = commands.add_parser("mirror-plan-show"); mirror_show.add_argument("plan_id"); mirror_show.set_defaults(handler=command_mirror_plan_show)
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
