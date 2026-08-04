from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def atomic_write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def stable_id(value: object) -> str:
    return sha256(canonical(value).encode()).hexdigest()


class ExternalStorage:
    def __init__(self, root: Path):
        self.root = root

    def put(self, category: str, identifier: str, value: object) -> Path:
        return atomic_write(self.root / category / f"{identifier}.json", asdict(value) if hasattr(value, "__dataclass_fields__") else value)

    def get(self, category: str, identifier: str) -> dict[str, object]:
        return json.loads((self.root / category / f"{identifier}.json").read_text(encoding="utf-8"))

    def list(self, category: str) -> tuple[dict[str, object], ...]:
        directory = self.root / category
        return tuple(json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))) if directory.is_dir() else ()
