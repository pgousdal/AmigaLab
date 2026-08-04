"""Small read-only WSGI catalog application (stdlib only)."""
from __future__ import annotations
from dataclasses import dataclass
from html import escape
import json
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, unquote
from wsgiref.simple_server import make_server

from ..catalog.sqlite_index import CatalogIndex, verify_catalog


@dataclass(frozen=True)
class WebConfig:
    database: Path
    bind: str = "127.0.0.1"
    port: int = 8787
    page_size: int = 25
    max_page_size: int = 100
    allow_file_downloads: bool = False
    enabled: bool = False

    def validate(self):
        import ipaddress
        try: ipaddress.ip_address(self.bind)
        except ValueError as error: raise ValueError("invalid AmigaLab web bind address") from error
        if not 1 <= self.port <= 65535: raise ValueError("invalid AmigaLab web port")
        if not 1 <= self.page_size <= self.max_page_size <= 1000: raise ValueError("invalid AmigaLab web page limits")
        return self


def _json(start, status, value):
    body = json.dumps(value, sort_keys=True, indent=2).encode()
    start(status, [("Content-Type", "application/json; charset=utf-8"), ("Content-Security-Policy", "default-src 'self'; object-src 'none'"), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"), ("Permissions-Policy", "geolocation=(), camera=(), microphone=()"), ("Cross-Origin-Resource-Policy", "same-origin"), ("Cross-Origin-Opener-Policy", "same-origin"), ("Content-Length", str(len(body)))])
    return [body]


def _html(start, status, title, body):
    content = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><title>" + escape(title) +
               "</title><meta name='viewport' content='width=device-width,initial-scale=1'>" +
               "<style>body{font:16px sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}a{color:#0645ad}code,pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{padding:.35rem;border-bottom:1px solid #ccc}</style></head><body>" + body + "</body></html>").encode()
    start(status, [("Content-Type", "text/html; charset=utf-8"), ("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; object-src 'none'"), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"), ("Permissions-Policy", "geolocation=(), camera=(), microphone=()"), ("Cross-Origin-Resource-Policy", "same-origin"), ("Cross-Origin-Opener-Policy", "same-origin"), ("Content-Length", str(len(content)))])
    return [content]


def create_app(config: WebConfig):
    config.validate()
    index = CatalogIndex(config.database)

    def app(environ, start_response):
        if environ.get("REQUEST_METHOD", "GET") != "GET":
            return _json(start_response, "405 Method Not Allowed", {"error": "read-only application"})
        path = unquote(environ.get("PATH_INFO", "/"))
        if ".." in Path(path).parts or path.startswith("//"):
            return _json(start_response, "400 Bad Request", {"error": "invalid path"})
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        if any(len(value[0]) > 1000 for value in query.values()):
            return _json(start_response, "400 Bad Request", {"error": "query parameter too long"})
        if path == "/health":
            status = verify_catalog(config.database) if config.database.is_file() else {"valid": False, "error": "catalog unavailable"}
            return _json(start_response, "200 OK", {"status": "ok" if status.get("valid") else "degraded", "catalog": status, "version": "amigalab-web-1"})
        if not config.database.is_file():
            return _html(start_response, "503 Service Unavailable", "Catalog unavailable", "<h1>Catalog unavailable</h1><p>Run <code>python3 scripts/amigalab-import.py catalog-build</code>.</p>")
        try:
            def document_response(value):
                etag = '"' + sha256(json.dumps(value, sort_keys=True).encode()).hexdigest() + '"'
                if environ.get("HTTP_IF_NONE_MATCH") == etag:
                    start_response("304 Not Modified", [("ETag", etag)]); return [b""]
                return _json(start_response, "200 OK", {"api_version": "v1", "entity_type": value.get("entity_type"), "document": value, "trace_hint": "object-trace " + value.get("object_id", "") if value.get("object_id") else ""})
            if path in {"/", "/search"}:
                q = query.get("q", [""])[0]; rows = index.search(q or "*", collection=query.get("collection", [None])[0], entity_type=query.get("type", [None])[0], extension=query.get("extension", [None])[0], path_prefix=query.get("path-prefix", [None])[0], limit=min(int(query.get("limit", [config.page_size])[0]), config.max_page_size), offset=max(0, int(query.get("offset", [0])[0]))) if q else []
                body = "<h1>AmigaLab Catalog</h1><form action='/search'><input name='q' value='" + escape(q) + "' autofocus><button>Search</button></form><p>" + str(len(rows)) + " results</p><ul>" + "".join("<li><a href='/catalog/documents/" + escape(item[0]) + "'>" + escape(json.loads(item[0]).get("title", item[0])) + "</a> " + escape(json.loads(item[0]).get("relative_path", "")) + "</li>" for item in rows) + "</ul>"
                return _html(start_response, "200 OK", "AmigaLab Catalog", body)
            if path == "/api/v1/search":
                q = query.get("q", [""])[0]
                if not q: return _json(start_response, "400 Bad Request", {"error": "q is required"})
                limit = min(int(query.get("limit", [config.page_size])[0]), config.max_page_size)
                rows = index.search(q, collection=query.get("collection", [None])[0], entity_type=query.get("type", [None])[0], limit=limit, offset=max(0, int(query.get("offset", [0])[0])))
                return _json(start_response, "200 OK", {"query": q, "results": [{**json.loads(raw), "rank": rank} for raw, rank in rows]})
            if path == "/api/v1/catalog/stats":
                return _json(start_response, "200 OK", {"api_version": "v1", "stats": index.stats()})
            if path.startswith("/api/v1/catalog/documents/"):
                value = index.show(path.rsplit("/", 1)[-1])
                return document_response(value) if value else _json(start_response, "404 Not Found", {"error": "document not found"})
            for prefix in ("/api/v1/objects/", "/api/v1/files/", "/api/v1/media/", "/api/v1/sources/", "/api/v1/verification-reports/"):
                if path.startswith(prefix):
                    canonical = path[len(prefix):]; kind = prefix.split("/")[3].rstrip('s')
                    value = index.show(kind + ":" + canonical)
                    return document_response(value) if value else _json(start_response, "404 Not Found", {"error": "entity not found"})
            for prefix, kind in (("/api/v1/traces/objects/", "object"), ("/api/v1/traces/files/", "file"), ("/api/v1/traces/media/", "media")):
                if path.startswith(prefix):
                    canonical = path[len(prefix):]; value = index.show(kind + ":" + canonical)
                    return _json(start_response, "200 OK", {"api_version": "v1", "kind": kind, "canonical_id": canonical, "found": bool(value), "document": value})
            if path.startswith("/catalog/documents/"):
                document_id = path.rsplit("/", 1)[-1]; value = index.show(document_id)
                if value is None: return _json(start_response, "404 Not Found", {"error": "document not found"})
                heading = value.get("title") or value.get("display_name") or value["id"]
                body = "<a href='/'>Home</a><h1>" + escape(heading) + "</h1><p><strong>" + escape(value.get("entity_type", "")) + "</strong> — " + escape(value.get("verification_status", "unverified")) + "</p>"
                body += "<dl>" + "".join("<dt>" + escape(key) + "</dt><dd>" + escape(str(value.get(key, ""))) + "</dd>" for key in ("canonical_id", "collection", "relative_path", "size", "license_profile", "media_classification", "provenance_summary")) + "</dl>"
                if value.get("sidecar_role") == "sidecar" or value.get("entity_type") == "readme": body += "<h2>Readme</h2><pre>" + escape(value.get("searchable_text", "")) + "</pre>"
                body += "<h2>Derived record</h2><pre>" + escape(json.dumps(value, indent=2, sort_keys=True)) + "</pre>"
                return _html(start_response, "Catalog document", body)
            if path.startswith("/browse/"):
                prefix = path[len("/browse/"):].strip("/"); rows = index.search("*", collection=prefix.split("/", 1)[0] if prefix else None, path_prefix=prefix or None, limit=config.max_page_size)
                return _html(start_response, "200 OK", "Browse", "<h1>Browse " + escape(prefix or "root") + "</h1><ul>" + "".join("<li>" + escape(json.loads(raw).get("relative_path", "")) + "</li>" for raw, _ in rows) + "</ul>")
            return _json(start_response, "404 Not Found", {"error": "not found"})
        except (ValueError, OSError):
            return _json(start_response, "400 Bad Request", {"error": "invalid catalog request"})
    return app


def run(config: WebConfig):
    config.validate()
    if config.bind != "127.0.0.1" and not config.enabled:
        raise ValueError("remote AmigaLab web binding requires explicit enablement")
    with make_server(config.bind, config.port, create_app(config)) as server:
        server.serve_forever()
