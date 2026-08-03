#!/usr/bin/env python3
"""Verify an archive collection against its manifest and checksum file."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from archive_lib import ArchiveError, EXIT_INVALID, verify_collection


def _report(label: str, paths: tuple[str, ...]) -> None:
    for path in paths:
        print(f"{label}: {path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", type=Path, help="collection directory to verify")
    parser.add_argument("--metadata-dir", required=True, type=Path, help="separate directory containing the manifest")
    args = parser.parse_args()
    try:
        result = verify_collection(args.collection, args.metadata_dir)
    except ArchiveError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    _report("missing", result.missing)
    _report("changed", result.changed)
    _report("extra", result.extra)
    _report("checksum mismatch", result.checksum_mismatches)
    if result.valid:
        print(f"Archive verification passed: {args.collection}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
