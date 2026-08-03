#!/usr/bin/env python3
"""Metadata-first, non-destructive import command for AmigaLab."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from preservation.importer import SUPPORTED_SOURCE_KINDS, import_source, scan
from preservation.models import Source
from preservation.storage import MetadataStore
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
    _, metadata_root, _ = roots(args)
    store = MetadataStore(metadata_root)
    store.save_source(Source(args.id, args.name, args.kind, args.location))
    print(f"Registered source: {args.id}")
    return 0


def command_scan(args: argparse.Namespace) -> int:
    archive_root, metadata_root, _ = roots(args)
    print_preview(scan(Path(args.location), args.collection, MetadataStore(metadata_root), archive_root))
    return 0


def command_import(args: argparse.Namespace) -> int:
    archive_root, metadata_root, staging_root = roots(args)
    store = MetadataStore(metadata_root)
    source = store.get_source(args.source)
    if source is None:
        raise ValueError(f"Unknown source ID: {args.source}. Register it with source-add first.")
    print_preview(import_source(Path(args.location), args.collection, source, store, archive_root, staging_root, args.yes))
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
    source_add.set_defaults(handler=command_source_add)

    scan_command = commands.add_parser("scan", help="read-only source preview")
    scan_command.add_argument("location")
    scan_command.add_argument("--collection", required=True)
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
