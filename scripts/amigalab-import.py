#!/usr/bin/env python3
"""Metadata-first, non-destructive import command for AmigaLab."""

from __future__ import annotations

import argparse
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
from preservation.verification import append_verification, verify_object


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
