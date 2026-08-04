import json
import pytest
from scripts.preservation.catalog.meilisearch import MeiliClient, validate_endpoint, batches
from scripts.preservation.catalog.models import CatalogDocument
from scripts.preservation.catalog.sqlite_index import build_catalog
from scripts.preservation.web import WebConfig, create_app


def test_meilisearch_namespacing_and_batches():
    assert validate_endpoint("http://127.0.0.1:7700")
    assert not validate_endpoint("https://example.invalid")
    with pytest.raises(ValueError): MeiliClient("http://127.0.0.1:7700", "search")
    docs = [CatalogDocument(str(i), "file", str(i)) for i in range(3)]
    assert [len(batch) for batch in batches(docs, 2)] == [2, 1]


def test_api_stats_and_missing_document(tmp_path):
    db = tmp_path / "catalog.db"; build_catalog(tmp_path / "metadata", tmp_path / "archive", db)
    app = create_app(WebConfig(db)); results = {}
    def start(status, headers): results["status"] = status
    body = b"".join(app({"PATH_INFO": "/api/v1/catalog/stats", "QUERY_STRING": "", "REQUEST_METHOD": "GET"}, start))
    assert results["status"] == "200 OK" and b"api_version" in body
    body = b"".join(app({"PATH_INFO": "/api/v1/catalog/documents/object:nope", "QUERY_STRING": "", "REQUEST_METHOD": "GET"}, start))
    assert results["status"] == "404 Not Found"
