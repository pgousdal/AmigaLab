"""State-aware, side-effect-scoped transaction recovery executor."""

from __future__ import annotations

from dataclasses import dataclass

from .transactions import RECOVERY_ACTIONS, TransactionStore
from .models import TransactionEntry


@dataclass(frozen=True)
class RecoveryResult:
    entry_id: str
    action: str
    state: str
    changed: bool
    diagnostic: str = ""


class RecoveryExecutor:
    def __init__(self, store: TransactionStore, max_actions: int = 16):
        self.store = store
        self.max_actions = max_actions

    def execute(self, entry: TransactionEntry, action: str | None = None) -> RecoveryResult:
        action = action or RECOVERY_ACTIONS.get(entry.state, "fail-permanently")
        if action == "skip-completed":
            return RecoveryResult(entry.id, action, entry.state, False)
        if action == "wait-for-conflict":
            return RecoveryResult(entry.id, action, entry.state, False, "blocking conflict remains")
        if action == "fail-permanently":
            return RecoveryResult(entry.id, action, "failed", True, "unsupported recovery action")
        target = {"start-entry": "opening-source", "restart-stream": "opening-source", "validate-staging": "staged", "rehash-staging": "ready-to-copy", "copy-from-staging": "copying", "finalize-temporary-destination": "verifying", "verify-destination": "metadata-writing", "complete-metadata": "completed", "complete-provenance": "provenance-only", "complete-import-event": "metadata-writing", "complete-relationships": "metadata-writing", "complete-verification-event": "completed"}.get(action)
        if target is None or target == entry.state:
            return RecoveryResult(entry.id, action, entry.state, False)
        updated = self.store.transition(entry, target, target, action)
        return RecoveryResult(entry.id, action, updated.state, True)
