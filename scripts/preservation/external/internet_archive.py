from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .base import ExternalProvider
from .models import ExternalFile, ExternalItem, ExternalSource


class InternetArchiveProvider(ExternalProvider):
    def __init__(self, *, timeout: float = 20, user_agent: str = "AmigaLab/2.15", opener=urlopen):
        self.timeout = timeout
        self.user_agent = user_agent
        self.opener = opener

    def _get(self, url: str) -> dict[str, object]:
        if not url.startswith("https://archive.org/"):
            raise ValueError("provider URL is outside the official Internet Archive endpoint")
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        with self.opener(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _file(raw: dict[str, object]) -> ExternalFile:
        return ExternalFile(str(raw.get("name", "")), int(raw["size"]) if raw.get("size") not in (None, "") else None,
                            str(raw.get("format", "")), "derivative" if str(raw.get("source", "")).lower() == "derivative" else "original",
                            str(raw.get("md5", "")), str(raw.get("sha1", "")), str(raw.get("crc32", "")), str(raw.get("mtime", "")),
                            f"https://archive.org/download/{raw.get('identifier', '')}/{quote(str(raw.get('name', '')))}", bool(raw.get("private", False)))

    def inspect(self, source: ExternalSource, *, page_size: int = 50, page: int = 1) -> tuple[dict[str, object], tuple[ExternalItem, ...], bool]:
        query = quote(f"collection:{source.upstream_identifier}")
        search = self._get(f"https://archive.org/advancedsearch.php?q={query}&fl[]=identifier&rows={page_size}&page={page}&output=json")
        docs = search.get("response", {}).get("docs", []) if isinstance(search.get("response"), dict) else []
        items: list[ExternalItem] = []
        for doc in docs:
            identifier = str(doc.get("identifier", ""))
            metadata = self._get(f"https://archive.org/metadata/{quote(identifier)}")
            meta = metadata.get("metadata", {}) if isinstance(metadata.get("metadata"), dict) else {}
            files = tuple(self._file({**file, "identifier": identifier}) for file in metadata.get("files", []) if isinstance(file, dict) and file.get("name"))
            subjects = meta.get("subject", ())
            if isinstance(subjects, str): subjects = (subjects,)
            items.append(ExternalItem(identifier, str(meta.get("title", "")), str(meta.get("description", "")), str(meta.get("creator", "")), str(meta.get("date", "")), tuple(str(x) for x in subjects), str(meta.get("mediatype", "")), tuple(str(x) for x in meta.get("collection", ())) if isinstance(meta.get("collection", ()), list) else (), str(meta.get("licenseurl", "")), "restricted" if metadata.get("is_dark", False) else "public", f"https://archive.org/details/{identifier}", files))
        total = search.get("response", {}).get("numFound", len(items)) if isinstance(search.get("response"), dict) else len(items)
        complete = page * page_size >= int(total)
        return {"identifier": source.upstream_identifier, "title": source.name, "total": total, "page": page, "page_size": page_size}, tuple(items), complete
