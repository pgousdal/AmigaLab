#!/usr/bin/env python3
"""Build a deterministic manifest and SHA-256 checksum file for a collection."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from archive_lib import ArchiveError, build_collection_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", type=Path, help="collection directory to scan")
    parser.add_argument("--metadata-dir", required=True, type=Path, help="separate directory for AmigaLab metadata")
    args = parser.parse_args()
    try:
        entries = build_collection_manifest(args.collection, args.metadata_dir)
    except ArchiveError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote manifest for {args.collection}: {len(entries)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
