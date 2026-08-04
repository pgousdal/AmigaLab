from __future__ import annotations

from dataclasses import asdict
from .models import ExternalSnapshot
from .storage import stable_id


def diff_snapshots(old: ExternalSnapshot, new: ExternalSnapshot) -> dict[str, object]:
    before = {item.identifier: item for item in old.items}
    after = {item.identifier: item for item in new.items}
    changes: list[dict[str, object]] = []
    for identifier in sorted(set(before) | set(after)):
        if identifier not in before: changes.append({"type": "new", "severity": "review", "item": identifier})
        elif identifier not in after: changes.append({"type": "removed-upstream", "severity": "review", "item": identifier})
        elif asdict(before[identifier]) != asdict(after[identifier]): changes.append({"type": "metadata-changed", "severity": "important", "item": identifier})
    return {"id": stable_id({"old": old.fingerprint, "new": new.fingerprint, "changes": changes}), "old_snapshot_id": old.id, "new_snapshot_id": new.id, "changes": changes, "count": len(changes)}
