from pathlib import Path
from scripts.preservation.catalog.readme import decode_readme
from scripts.preservation.catalog.builder import build_documents
from scripts.preservation.catalog.sqlite_index import build_catalog, CatalogIndex, verify_catalog


def test_readme_parser_extracts_fields_and_raw_text(tmp_path):
    path = tmp_path / "x.readme"
    path.write_text("Description: Directory utility\nAuthor: Ada\nVersion: 1.0\n", encoding="utf-8")
    parsed = decode_readme(path)
    assert parsed.fields["author"] == "Ada"
    assert "Directory utility" in parsed.raw_text


def test_binary_readme_is_safe(tmp_path):
    path = tmp_path / "x.readme"; path.write_bytes(b"\x00\xff")
    parsed = decode_readme(path)
    assert parsed.encoding == "binary"
    assert parsed.raw_text == ""


def test_empty_catalog_build_and_verify(tmp_path):
    metadata, archive, database = tmp_path / "metadata", tmp_path / "archive", tmp_path / "catalog.db"
    metadata.mkdir(); archive.mkdir()
    result = build_catalog(metadata, archive, database)
    assert result["document_count"] == 0
    assert verify_catalog(database)["valid"]


def test_catalog_search_is_deterministic(tmp_path):
    metadata, archive, database = tmp_path / "metadata", tmp_path / "archive", tmp_path / "catalog.db"
    metadata.mkdir(); archive.mkdir(); build_catalog(metadata, archive, database)
    assert CatalogIndex(database).search("missing") == []
