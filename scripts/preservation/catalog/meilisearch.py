"""Optional Meilisearch adapter; it never reads preservation trees directly."""
from __future__ import annotations
import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from dataclasses import dataclass
import json
from .models import CatalogDocument


def validate_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}


def batches(documents: list[CatalogDocument], size: int = 100):
    for start in range(0, len(documents), max(1, size)):
        yield [doc.as_dict() for doc in documents[start:start + max(1, size)]]


@dataclass(frozen=True)
class MeiliResult:
    status: str
    added: int = 0
    updated: int = 0
    removed: int = 0
    errors: tuple[str, ...] = ()


class MeiliClient:
    def __init__(self, endpoint: str, index: str, timeout: int = 15, api_key: str = ""):
        if not validate_endpoint(endpoint):
            raise ValueError("Meilisearch endpoint must be localhost HTTP")
        if not index.startswith("amigalab_"):
            raise ValueError("Meilisearch index must be AmigaLab-namespaced")
        self.endpoint, self.index, self.timeout, self.api_key = endpoint.rstrip("/"), index, timeout, api_key

    def _request(self, method, path, body=None):
        headers = {"Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = "Bearer " + self.api_key
        request = Request(self.endpoint + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode() or "{}")

    def health(self):
        return self._request("GET", "/health")

    def sync(self, documents, batch_size=500):
        added = updated = 0
        try:
            for batch in batches(documents, batch_size):
                self._request("POST", f"/indexes/{self.index}/documents", batch)
                added += len(batch)
            return MeiliResult("success", added=added, updated=updated)
        except (HTTPError, URLError, OSError, ValueError) as error:
            return MeiliResult("failed", errors=(str(error),))
