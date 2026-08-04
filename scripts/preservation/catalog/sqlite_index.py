from __future__ import annotations
import json, sqlite3, tempfile
from pathlib import Path
from .builder import build_documents

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE catalog_documents (id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, canonical_id TEXT NOT NULL, collection_name TEXT, title TEXT, display_name TEXT, historical_filename TEXT, relative_path TEXT, parent_path TEXT, extension TEXT, media_type TEXT, size INTEGER, hashes TEXT, object_id TEXT, file_id TEXT, media_id TEXT, primary_file_id TEXT, sidecar_role TEXT, source_ids TEXT, license_profile TEXT, media_classification TEXT, export_allowed INTEGER, verification_status TEXT, latest_verification_timestamp TEXT, provenance_summary TEXT, searchable_text TEXT, keywords TEXT, source_fingerprint TEXT, fingerprint TEXT NOT NULL, document_json TEXT NOT NULL);
CREATE VIRTUAL TABLE catalog_fts USING fts5(document_id UNINDEXED, title, filename, path, description, searchable_text, content='');
CREATE TABLE catalog_builds (id TEXT PRIMARY KEY, completed_at TEXT, document_count INTEGER, content_fingerprint TEXT, warnings TEXT, errors TEXT);
"""

class CatalogIndex:
    def __init__(self, database: Path): self.database = database

    def search(self, query: str, *, collection=None, entity_type=None, extension=None, path_prefix=None, license_profile=None, verification=None, source=None, limit=20, offset=0):
        clauses = ["catalog_fts MATCH ?"]; params = [query]
        if collection: clauses.append("d.collection_name = ?"); params.append(collection)
        if entity_type: clauses.append("d.entity_type = ?"); params.append(entity_type)
        if extension: clauses.append("d.extension = ?"); params.append(extension.lstrip('.').lower())
        if path_prefix: clauses.append("d.relative_path LIKE ?"); params.append(path_prefix.rstrip('/') + '/%')
        if license_profile: clauses.append("d.license_profile = ?"); params.append(license_profile)
        if verification: clauses.append("d.verification_status = ?"); params.append(verification)
        if source: clauses.append("d.source_ids LIKE ?"); params.append('%"' + source + '"%')
        params.extend([limit, offset])
        with sqlite3.connect(self.database) as db:
            statement = "SELECT d.document_json, bm25(catalog_fts) AS rank FROM catalog_fts JOIN catalog_documents d ON d.id=catalog_fts.document_id WHERE " + " AND ".join(clauses) + " ORDER BY rank, d.id LIMIT ? OFFSET ?"
            try:
                return db.execute(statement, params).fetchall()
            except sqlite3.OperationalError:
                # User text is treated as a literal token sequence, never as
                # unchecked FTS syntax.
                params[0] = '"' + query.replace('"', ' ') + '"'
                return db.execute(statement, params).fetchall()

    def show(self, document_id):
        with sqlite3.connect(self.database) as db:
            row = db.execute("SELECT document_json FROM catalog_documents WHERE id=?", (document_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def stats(self):
        with sqlite3.connect(self.database) as db:
            rows = db.execute("SELECT entity_type, count(*) FROM catalog_documents GROUP BY entity_type ORDER BY entity_type").fetchall()
        return {key: value for key, value in rows}


def build_catalog(metadata_root: Path, archive_root: Path, database: Path, max_text_bytes=1_048_576, strict=False):
    documents = build_documents(metadata_root, archive_root, max_text_bytes)
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(temporary) as db:
        db.executescript(SCHEMA)
        for doc in documents:
            value = doc.as_dict()
            db.execute("INSERT INTO catalog_documents VALUES (" + ",".join("?" for _ in range(30)) + ")", (
                doc.id, doc.entity_type, doc.canonical_id, doc.collection, doc.title, doc.display_name, doc.historical_filename,
                doc.relative_path, doc.parent_path, doc.extension, doc.media_type, doc.size, json.dumps(doc.hashes, sort_keys=True),
                doc.object_id, doc.file_id, doc.media_id, doc.primary_file_id, doc.sidecar_role, json.dumps(doc.source_ids), doc.license_profile,
                doc.media_classification, int(doc.export_allowed), doc.verification_status, doc.latest_verification_timestamp, doc.provenance_summary,
                doc.searchable_text, json.dumps(doc.keywords), doc.source_fingerprint, doc.fingerprint, json.dumps(value, sort_keys=True)))
            db.execute("INSERT INTO catalog_fts(document_id,title,filename,path,description,searchable_text) VALUES (?,?,?,?,?,?)", (doc.id, doc.title, doc.historical_filename, doc.relative_path, doc.provenance_summary, doc.searchable_text))
        db.commit()
    temporary.replace(database)
    return {"document_count": len(documents), "object_count": sum(d.entity_type == "object" for d in documents), "file_count": sum(d.entity_type == "file" for d in documents), "readme_count": sum(d.entity_type == "readme" for d in documents), "media_count": sum(d.entity_type == "media" for d in documents), "source_count": sum(d.entity_type == "source" for d in documents)}


def verify_catalog(database: Path) -> dict:
    with sqlite3.connect(database) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if "catalog_documents" not in tables or "catalog_fts" not in tables: return {"valid": False, "error": "catalog schema or FTS5 is missing"}
        documents = db.execute("SELECT count(*) FROM catalog_documents").fetchone()[0]
        fts = db.execute("SELECT count(*) FROM catalog_fts").fetchone()[0]
    return {"valid": documents == fts, "documents": documents, "fts_rows": fts}
