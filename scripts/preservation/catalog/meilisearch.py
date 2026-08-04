"""Optional Meilisearch adapter; it never reads preservation trees directly."""
from __future__ import annotations
import json
from urllib.parse import urlparse
from .models import CatalogDocument


def validate_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}


def batches(documents: list[CatalogDocument], size: int = 100):
    for start in range(0, len(documents), max(1, size)):
        yield [doc.as_dict() for doc in documents[start:start + max(1, size)]]

