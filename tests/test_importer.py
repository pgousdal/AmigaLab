from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preservation.importer import import_source, scan
from scripts.preservation.index import build_index, drop_index, query
from scripts.preservation.models import Source
from scripts.preservation.storage import MetadataStore


def setup_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    archive_root = tmp_path / "archive"
    metadata_root = tmp_path / "metadata"
    staging_root = tmp_path / "staging"
    return source, archive_root, metadata_root, staging_root


def test_source_registration_and_dry_run_scan_are_non_destructive(tmp_path: Path) -> None:
    source_path, archive_root, metadata_root, _ = setup_paths(tmp_path)
    (source_path / "tool.lha").write_bytes(b"tool")
    store = MetadataStore(metadata_root)
    store.save_source(Source("cd17", "Aminet CD 17", "directory", str(source_path)))

    preview = scan(source_path, "aminet", store, archive_root)

    assert store.get_source("cd17").name == "Aminet CD 17"
    assert preview.new_objects == 1
    assert not archive_root.exists()
    assert not list((metadata_root / "objects").glob("*.json"))


def test_import_requires_confirmation_and_preserves_paths(tmp_path: Path) -> None:
    source_path, archive_root, metadata_root, staging_root = setup_paths(tmp_path)
    nested = source_path / "util" / "arc"
    nested.mkdir(parents=True)
    (nested / "tool.lha").write_bytes(b"tool")
    (nested / "tool.readme").write_text("readme")
    source = Source("cd17", "Aminet CD 17", "directory", str(source_path))
    store = MetadataStore(metadata_root)

    try:
        import_source(source_path, "aminet", source, store, archive_root, staging_root, False)
    except PermissionError:
        pass
    else:
        raise AssertionError("import did not require confirmation")
    import_source(source_path, "aminet", source, store, archive_root, staging_root, True)

    assert (archive_root / "aminet/util/arc/tool.lha").read_bytes() == b"tool"
    assert (archive_root / "aminet/util/arc/tool.readme").read_text() == "readme"
    assert (staging_root / "cd17/util/arc/tool.lha").exists()
    assert len(store.list_objects()) == 1


def test_duplicate_hash_adds_provenance_without_duplicate_storage(tmp_path: Path) -> None:
    source_path, archive_root, metadata_root, staging_root = setup_paths(tmp_path)
    (source_path / "tool.lha").write_bytes(b"tool")
    store = MetadataStore(metadata_root)
    first = Source("live", "Aminet Live", "directory", str(source_path))
    second = Source("backup", "Personal backup", "directory", str(source_path))
    import_source(source_path, "aminet", first, store, archive_root, staging_root, True)
    import_source(source_path, "aminet", second, store, archive_root, staging_root, True)

    object_ = store.list_objects()[0]
    assert object_.provenance_source_ids == ("live", "backup")
    assert len(list((archive_root / "aminet").rglob("*"))) == 1


def test_import_events_and_sqlite_index_rebuild_from_metadata(tmp_path: Path) -> None:
    source_path, archive_root, metadata_root, staging_root = setup_paths(tmp_path)
    (source_path / "DiskMaster2.lha").write_bytes(b"tool")
    store = MetadataStore(metadata_root)
    source = Source("live", "Aminet Live", "directory", str(source_path))
    import_source(source_path, "aminet", source, store, archive_root, staging_root, True)
    database = metadata_root / "index.db"

    assert len(list((metadata_root / "imports").glob("*.json"))) == 1
    assert build_index(metadata_root, database) == 1
    assert query(database, "DiskMaster")
    drop_index(database)
    assert not database.exists()
    assert store.list_objects()
