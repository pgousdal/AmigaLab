from __future__ import annotations
from hashlib import sha256
import json


def document_fingerprint(value: dict) -> str:
    filtered = {k: v for k, v in value.items() if k not in {"fingerprint", "created_at", "updated_at"}}
    return sha256(json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
