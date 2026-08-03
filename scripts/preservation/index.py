"""Disposable SQLite index rebuilt from canonical preservation metadata."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .storage import MetadataStore


def build_index(metadata_root: Path, database_path: Path) -> int:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            "DROP TABLE IF EXISTS files;"
            "CREATE TABLE files (object_id TEXT, collection TEXT, path TEXT, sha256 TEXT);"
            "CREATE INDEX files_sha256 ON files (sha256);"
        )
        rows = [
            (object_.id, object_.original_collection, file.original_relative_path, file.hashes.sha256)
            for object_ in MetadataStore(metadata_root).list_objects()
            for file in object_.files
        ]
        connection.executemany("INSERT INTO files VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def drop_index(database_path: Path) -> None:
    database_path.unlink(missing_ok=True)


def query(database_path: Path, term: str) -> list[tuple[str, str, str, str]]:
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            "SELECT object_id, collection, path, sha256 FROM files WHERE path LIKE ? OR sha256 = ? ORDER BY path",
            (f"%{term}%", term),
        ).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-root", type=Path, default=Path("/srv/amigalab/metadata"))
    parser.add_argument("--database", type=Path, default=Path("/srv/amigalab/metadata/index.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build-index")
    commands.add_parser("drop-index")
    query_command = commands.add_parser("query")
    query_command.add_argument("term")
    args = parser.parse_args()
    if args.command == "build-index":
        print(f"Indexed {build_index(args.metadata_root, args.database)} file(s)")
    elif args.command == "drop-index":
        drop_index(args.database)
    else:
        for row in query(args.database, args.term):
            print("\t".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
