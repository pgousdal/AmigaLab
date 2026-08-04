"""State-aware, side-effect-scoped transaction recovery executor."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .transactions import RECOVERY_ACTIONS, TransactionStore
from .models import TransactionEntry
from .services import atomic_copy, validate_staging, verify_destination


@dataclass(frozen=True)
class RecoveryResult:
    entry_id: str
    action: str
    state: str
    changed: bool
    diagnostic: str = ""


@dataclass(frozen=True)
class RecoveryContext:
    """Filesystem roots for concrete recovery actions.

    The context is optional to preserve the small state-machine API used by
    older callers.  When supplied, filesystem actions validate and operate on
    transaction-owned staging and destination paths only.
    """

    staging_root: Path
    destination_root: Path


class RecoveryExecutor:
    def __init__(self, store: TransactionStore, max_actions: int = 16, context: RecoveryContext | None = None):
        self.store = store
        self.max_actions = max_actions
        self.context = context

    def execute(self, entry: TransactionEntry, action: str | None = None) -> RecoveryResult:
        action = action or RECOVERY_ACTIONS.get(entry.state, "fail-permanently")
        if action == "skip-completed":
            return RecoveryResult(entry.id, action, entry.state, False)
        if action == "wait-for-conflict":
            return RecoveryResult(entry.id, action, entry.state, False, "blocking conflict remains")
        if action == "fail-permanently":
            if entry.state != "failed":
                updated = self.store.transition(entry, "failed", "failed", action, "permanent recovery failure")
                return RecoveryResult(entry.id, action, updated.state, True, "permanent recovery failure")
            return RecoveryResult(entry.id, action, entry.state, False, "permanent recovery failure")

        # Concrete filesystem operations.  They intentionally do not create
        # preservation metadata; that is handled by the metadata service after
        # destination verification and is therefore independently resumable.
        if self.context is not None:
            if action in {"validate-staging", "rehash-staging"}:
                result = validate_staging(entry, self.context.staging_root)
                if result.status != "valid":
                    return RecoveryResult(entry.id, action, entry.state, False, result.reason)
                updated = replace(entry, observed_hashes=result.hashes, bytes_processed=result.size)
                self.store.save_entry(updated)
                if action == "rehash-staging" and entry.state == "hashing":
                    updated = self.store.transition(updated, "ready-to-copy", "hashing", action)
                elif action == "validate-staging" and entry.state == "staging":
                    updated = self.store.transition(updated, "staged", "staging", action)
                return RecoveryResult(entry.id, action, updated.state, True)
            if action in {"copy-from-staging", "finalize-temporary-destination"}:
                staged = validate_staging(entry, self.context.staging_root)
                if staged.status != "valid":
                    return RecoveryResult(entry.id, action, entry.state, False, staged.reason)
                target = Path(entry.target_path)
                if action == "copy-from-staging" and target.exists():
                    verified = verify_destination(target, self.context.destination_root, staged.hashes)
                    if verified.status != "valid":
                        return RecoveryResult(entry.id, action, entry.state, False, "blocking destination conflict")
                else:
                    if not str(target.resolve()).startswith(str(self.context.destination_root.resolve()) + "/"):
                        return RecoveryResult(entry.id, action, entry.state, False, "destination escapes root")
                    atomic_copy(Path(entry.staging_path), target)
                if entry.state in {"staged", "ready-to-copy"}:
                    updated = self.store.transition(entry, "copying", "copying", action)
                    updated = self.store.transition(updated, "verifying", "verifying", "verify-destination")
                    return RecoveryResult(entry.id, action, updated.state, True)
            if action == "verify-destination":
                result = verify_destination(Path(entry.target_path), self.context.destination_root, entry.observed_hashes or entry.expected_hashes)
                if result.status != "valid":
                    return RecoveryResult(entry.id, action, entry.state, False, result.reason)
                updated = self.store.transition(entry, "metadata-writing", "metadata-writing", action) if entry.state == "verifying" else entry
                return RecoveryResult(entry.id, action, updated.state, True)
        target = {"start-entry": "opening-source", "restart-stream": "opening-source", "validate-staging": "staged", "rehash-staging": "ready-to-copy", "copy-from-staging": "copying", "finalize-temporary-destination": "verifying", "verify-destination": "metadata-writing", "complete-metadata": "completed", "complete-provenance": "provenance-only", "complete-import-event": "metadata-writing", "complete-relationships": "metadata-writing", "complete-verification-event": "completed"}.get(action)
        if target is None or target == entry.state:
            return RecoveryResult(entry.id, action, entry.state, False)
        updated = self.store.transition(entry, target, target, action)
        return RecoveryResult(entry.id, action, updated.state, True)
