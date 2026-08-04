from pathlib import Path
from scripts.preservation.catalog.sqlite_index import build_catalog
from scripts.preservation.web import WebConfig, create_app


def call(app, path, method="GET"):
    result = {}
    def start(status, headers): result.update(status=status, headers=dict(headers))
    body = b"".join(app({"PATH_INFO": path, "QUERY_STRING": "", "REQUEST_METHOD": method, "wsgi.url_scheme": "http"}, start))
    return result["status"], result["headers"], body


def test_web_config_localhost_default_and_health(tmp_path):
    db = tmp_path / "catalog.db"; build_catalog(tmp_path / "metadata", tmp_path / "archive", db)
    app = create_app(WebConfig(db))
    status, headers, body = call(app, "/health")
    assert status == "200 OK" and b'"status": "ok"' in body
    assert "Content-Security-Policy" in headers


def test_missing_catalog_is_clear(tmp_path):
    status, _, body = call(create_app(WebConfig(tmp_path / "missing.db")), "/")
    assert status == "503 Service Unavailable" and b"catalog-build" in body


def test_write_methods_are_rejected(tmp_path):
    db = tmp_path / "catalog.db"; build_catalog(tmp_path / "metadata", tmp_path / "archive", db)
    status, _, body = call(create_app(WebConfig(db)), "/", "POST")
    assert status == "405 Method Not Allowed" and b"read-only" in body


def test_invalid_path_is_rejected(tmp_path):
    db = tmp_path / "catalog.db"; build_catalog(tmp_path / "metadata", tmp_path / "archive", db)
    status, _, _ = call(create_app(WebConfig(db)), "/../etc")
    assert status == "400 Bad Request"
