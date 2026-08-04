from pathlib import Path

from scripts.preservation.events import EventStore, RelationshipRecord, VerificationRecord
from scripts.preservation.obligations import required_obligations


def test_verification_event_and_relationship_are_idempotent(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "metadata")
    verification = VerificationRecord("v", "entry:path:hash", "tx", "entry", "target", "initial-import", {"sha256": "a"}, {"sha256": "a"}, True)
    first = store.verification(verification)
    second = store.verification(verification)
    relationship = RelationshipRecord("r", "media:object:path", "imported-from", "media", "object", "source", "tx", "path", "target")
    relationship_first = store.relationship(relationship)
    relationship_second = store.relationship(relationship)
    assert first == second
    assert relationship_first == relationship_second
    assert first != relationship_first


def test_entry_obligations_are_explicit() -> None:
    assert "media-metadata" in required_obligations("preserve-media", "media-only")
    assert "object-metadata" in required_obligations("import-member", "members-only")
