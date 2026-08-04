"""Deterministic recovery planning, dry-runs, state, locks, and reports.

This module is deliberately filesystem-backed.  Plans, execution state, and
reports are canonical JSON documents and can be inspected or rebuilt without
SQLite.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .models import TransactionEntry
from .services import hash_file, validate_staging, verify_destination
from .recovery import RecoveryContext, RecoveryExecutor
from .transactions import TransactionStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _atomic_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


@dataclass(frozen=True)
class RecoveryAction:
    id: str
    entry_id: str
    operation: str
    status: str
    source_path: str
    staging_path: str
    destination_path: str
    preconditions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    obligations: tuple[str, ...] = ()
    expected_hashes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryPlan:
    id: str
    schema_version: int
    created_at: str
    identity: str
    source_path: str
    staging_path: str
    destination_path: str
    source_fingerprint: str
    actions: tuple[RecoveryAction, ...]
    preconditions: tuple[str, ...] = ()

    @staticmethod
    def deterministic_id(content: dict[str, object]) -> str:
        stable = dict(content)
        stable.pop("created_at", None)
        return sha256(_canonical(stable).encode()).hexdigest()

    def canonical_content(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("created_at", None)
        return data

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def _action_for(entry: TransactionEntry, staging_root: Path, destination_root: Path) -> RecoveryAction:
    expected = asdict(entry.expected_hashes) if entry.expected_hashes else {}
    status = "already_satisfied" if entry.state in {"completed", "reused", "skipped"} else "would_copy"
    action_id = sha256(f"{entry.id}:{entry.target_path}:copy".encode()).hexdigest()
    return RecoveryAction(
        id=action_id, entry_id=entry.id, operation="copy-and-verify", status=status,
        source_path=entry.source_path, staging_path=str(entry.staging_path),
        destination_path=str(entry.target_path),
        preconditions=("source fingerprint matches", "staging is contained", "destination is not conflicting"),
        obligations=("destination", "verification-event", "import-event"), expected_hashes=expected,
    )


def source_matches(plan: RecoveryPlan, source: Path) -> bool:
    """Compare the current source observation with the immutable plan."""
    if not source.exists():
        return False
    if source.is_file():
        hashes, size = hash_file(source)
        return sha256(f":{size}:{hashes.sha256}".encode()).hexdigest() == plan.source_fingerprint or hashes.sha256 == plan.source_fingerprint
    digest = sha256()
    for path in sorted(source.rglob("*")):
        if path.is_file():
            stat = path.stat()
            digest.update(path.relative_to(source).as_posix().encode())
            digest.update(f":{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest() == plan.source_fingerprint


def generate_plan(entries: Iterable[TransactionEntry], source_fingerprint: str, identity: str,
                  source_path: Path, staging_root: Path, destination_root: Path,
                  *, created_at: str | None = None) -> RecoveryPlan:
    ordered = tuple(sorted(entries, key=lambda item: (item.target_path, item.id)))
    actions = tuple(_action_for(entry, staging_root, destination_root) for entry in ordered)
    content = {
        "schema_version": 1, "identity": identity, "source_path": str(source_path),
        "staging_path": str(staging_root), "destination_path": str(destination_root),
        "source_fingerprint": source_fingerprint, "actions": [asdict(action) for action in actions],
        "preconditions": ["source fingerprint matches", "approved entry set is unchanged"],
    }
    return RecoveryPlan(RecoveryPlan.deterministic_id(content), 1, created_at or _now(), identity,
                        str(source_path), str(staging_root), str(destination_root), source_fingerprint,
                        actions, tuple(content["preconditions"]))


class RecoveryPlanStore:
    def __init__(self, root: Path):
        self.root = root

    def save(self, plan: RecoveryPlan) -> Path:
        return _atomic_json(self.root / "recovery-plans" / f"{plan.id}.json", asdict(plan))

    def load(self, plan_id: str) -> RecoveryPlan:
        data = json.loads((self.root / "recovery-plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
        data["actions"] = tuple(RecoveryAction(**item) for item in data["actions"])
        data["preconditions"] = tuple(data.get("preconditions", ()))
        return RecoveryPlan(**data)


@dataclass(frozen=True)
class ExecutionState:
    plan_id: str
    execution_id: str
    started_at: str
    updated_at: str
    status: str
    actions: dict[str, str] = field(default_factory=dict)
    completed_actions: tuple[str, ...] = ()
    skipped_actions: tuple[str, ...] = ()
    failed_actions: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    source_observations: dict[str, str] = field(default_factory=dict)
    destination_results: dict[str, str] = field(default_factory=dict)
    persisted_records: tuple[str, ...] = ()
    schema_version: int = 1
    revision: int = 0
    checkpoint: str = ""


class ExecutionStateStore:
    def __init__(self, root: Path):
        self.root = root

    def save(self, state: ExecutionState) -> Path:
        return _atomic_json(self.root / "recovery-executions" / f"{state.execution_id}.json", asdict(state))

    def load(self, execution_id: str) -> ExecutionState:
        data = json.loads((self.root / "recovery-executions" / f"{execution_id}.json").read_text(encoding="utf-8"))
        for key in ("completed_actions", "skipped_actions", "failed_actions", "failures", "persisted_records"):
            data[key] = tuple(data.get(key, ()))
        data.setdefault("schema_version", 1)
        data.setdefault("revision", 0)
        data.setdefault("checkpoint", "")
        return ExecutionState(**data)


@dataclass(frozen=True)
class AuditReport:
    plan_id: str
    execution_id: str | None
    result: str
    identity: str
    action_counts: dict[str, int]
    files_copied: tuple[str, ...] = ()
    files_reused: tuple[str, ...] = ()
    files_verified: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    blocked_actions: tuple[str, ...] = ()
    persisted_records: tuple[str, ...] = ()
    outstanding_obligations: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    resume_eligible: bool = False
    stale_plan: bool = False

    def human(self) -> str:
        return (f"recovery {self.result}: plan={self.plan_id} "
                f"copied={len(self.files_copied)} reused={len(self.files_reused)} "
                f"verified={len(self.files_verified)} blocked={len(self.blocked_actions)}")


class AuditReportStore:
    def __init__(self, root: Path):
        self.root = root

    def save(self, report: AuditReport, report_id: str | None = None) -> Path:
        identifier = report_id or report.execution_id or report.plan_id
        return _atomic_json(self.root / "recovery-reports" / f"{identifier}.json", asdict(report))

    def load(self, report_id: str) -> AuditReport:
        data = json.loads((self.root / "recovery-reports" / f"{report_id}.json").read_text(encoding="utf-8"))
        for key in ("files_copied", "files_reused", "files_verified", "conflicts", "blocked_actions", "persisted_records", "outstanding_obligations", "failures"):
            data[key] = tuple(data.get(key, ()))
        return AuditReport(**data)


def dry_run(plan: RecoveryPlan, entries: Iterable[TransactionEntry], staging_root: Path,
            destination_root: Path) -> AuditReport:
    counts: dict[str, int] = {}
    blocked: list[str] = []
    copied: list[str] = []
    reused: list[str] = []
    verified: list[str] = []
    for entry in sorted(entries, key=lambda item: item.id):
        staged = validate_staging(entry, staging_root)
        if staged.status != "valid":
            state = "invalid_source"
            blocked.append(entry.id)
        else:
            destination = verify_destination(Path(entry.target_path), destination_root, staged.hashes)
            if destination.status == "valid":
                state = "already_satisfied"
                reused.append(entry.target_path)
                verified.append(entry.target_path)
            elif Path(entry.target_path).exists():
                state = "conflict"
                blocked.append(entry.id)
            else:
                state = "would_copy"
                copied.append(entry.target_path)
        counts[state] = counts.get(state, 0) + 1
    result = "blocked" if blocked else "ready"
    return AuditReport(plan.id, None, result, plan.identity, counts, tuple(copied), tuple(reused), tuple(verified), blocked_actions=tuple(blocked), resume_eligible=not bool(blocked), stale_plan=bool(blocked and "invalid_source" in counts))


class PlanLock:
    def __init__(self, root: Path, plan_id: str):
        self.path = root / "recovery-locks" / f"{plan_id}.lock"
        self._owned = False

    def __enter__(self) -> "PlanLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise RuntimeError(f"recovery plan is already locked: {self.path}") from error
        os.write(fd, f"pid={os.getpid()}\n".encode())
        os.close(fd)
        self._owned = True
        return self

    def __exit__(self, *_: object) -> None:
        if self._owned:
            self.path.unlink(missing_ok=True)


@dataclass(frozen=True)
class OrchestrationResult:
    execution_id: str
    status: str
    report: AuditReport


class RecoveryOrchestrator:
    """Sequential, checkpointed execution of one immutable recovery plan."""

    def __init__(self, metadata_root: Path, plan_store: RecoveryPlanStore | None = None,
                 state_store: ExecutionStateStore | None = None):
        self.root = metadata_root
        self.plans = plan_store or RecoveryPlanStore(metadata_root)
        self.states = state_store or ExecutionStateStore(metadata_root)
        self.reports = AuditReportStore(metadata_root)

    def _checkpoint(self, state: ExecutionState, **changes: object) -> ExecutionState:
        updated = ExecutionState(**{**asdict(state), **changes,
                                   "updated_at": _now(), "revision": state.revision + 1})
        self.states.save(updated)
        return updated

    def execute(self, plan: RecoveryPlan, entries: Iterable[TransactionEntry], *,
                execution_id: str | None = None, resume: bool = False,
                source: Path | None = None) -> OrchestrationResult:
        execution_id = execution_id or str(uuid4())
        state = self.states.load(execution_id) if resume else ExecutionState(
            plan.id, execution_id, _now(), _now(), "created", checkpoint="initialized")
        if state.plan_id != plan.id:
            raise ValueError("execution state plan ID does not match recovery plan")
        if state.schema_version != plan.schema_version:
            raise ValueError("unsupported execution state schema")
        entry_map = {entry.id: entry for entry in entries}
        with PlanLock(self.root, plan.id):
            transaction_store = TransactionStore(self.root)
            for entry in entry_map.values():
                transaction_store.save_entry(entry)
            state = self._checkpoint(state, status="validating", checkpoint="plan-and-source-validation")
            if source is not None and not source_matches(plan, source):
                report = AuditReport(plan.id, execution_id, "stale", plan.identity, {"stale_plan": 1}, stale_plan=True)
                self.reports.save(report, execution_id)
                state = self._checkpoint(state, status="blocked", failures=("source fingerprint changed",), checkpoint="stale-source")
                return OrchestrationResult(execution_id, state.status, report)
            state = self._checkpoint(state, status="running", checkpoint="actions")
            counts: dict[str, int] = {}
            blocked: list[str] = []
            failures: list[str] = []
            copied: list[str] = []
            reused: list[str] = []
            verified: list[str] = []
            executor = RecoveryExecutor(transaction_store, context=RecoveryContext(Path(plan.staging_path), Path(plan.destination_path)))
            for action in plan.actions:
                prior = state.actions.get(action.id)
                entry = entry_map.get(action.entry_id)
                if entry is None:
                    failures.append(f"missing entry: {action.entry_id}")
                    counts["failed"] = counts.get("failed", 0) + 1
                    continue
                if prior == "completed":
                    counts["already_satisfied"] = counts.get("already_satisfied", 0) + 1
                    continue
                dependencies = [state.actions.get(dep) for dep in action.dependencies]
                if any(value not in {"completed", "skipped"} for value in dependencies):
                    blocked.append(action.id)
                    counts["blocked"] = counts.get("blocked", 0) + 1
                    state = self._checkpoint(state, actions={**state.actions, action.id: "blocked"}, checkpoint=f"blocked:{action.id}")
                    continue
                state = self._checkpoint(state, actions={**state.actions, action.id: "running"}, checkpoint=f"start:{action.id}")
                try:
                    result = executor.execute(entry, "copy-from-staging" if entry.state in {"staged", "ready-to-copy"} else None)
                    if result.diagnostic and not result.changed:
                        raise ValueError(result.diagnostic)
                    if result.state == "verifying":
                        refreshed = TransactionStore(self.root).list_entries(entry.transaction_id)
                        current = next(item for item in refreshed if item.id == entry.id)
                        result = executor.execute(current, "verify-destination")
                    if result.diagnostic and not result.changed:
                        raise ValueError(result.diagnostic)
                    state = self._checkpoint(state, actions={**state.actions, action.id: "completed"}, completed_actions=tuple(dict.fromkeys((*state.completed_actions, action.id))), checkpoint=f"complete:{action.id}")
                    counts["completed"] = counts.get("completed", 0) + 1
                    copied.append(action.destination_path)
                    verified.append(action.destination_path)
                except Exception as error:
                    failures.append(str(error))
                    counts["failed"] = counts.get("failed", 0) + 1
                    state = self._checkpoint(state, status="failed", actions={**state.actions, action.id: "failed"}, failed_actions=tuple(dict.fromkeys((*state.failed_actions, action.id))), failures=tuple(failures), checkpoint=f"failure:{action.id}")
                    break
            if failures:
                status = "failed"
            elif blocked:
                status = "blocked"
            else:
                status = "completed_with_skips" if counts.get("already_satisfied") else "completed"
            state = self._checkpoint(state, status=status, checkpoint="terminal")
            report = AuditReport(plan.id, execution_id, status, plan.identity, counts,
                                 tuple(copied), tuple(reused), tuple(verified),
                                 blocked_actions=tuple(blocked), failures=tuple(failures),
                                 resume_eligible=status not in {"completed", "completed_with_skips"})
            self.reports.save(report, execution_id)
            return OrchestrationResult(execution_id, status, report)

    def resume(self, plan: RecoveryPlan, execution_id: str, entries: Iterable[TransactionEntry], *, source: Path | None = None) -> OrchestrationResult:
        state = self.states.load(execution_id)
        if state.status in {"completed", "completed_with_skips"}:
            report = self.reports.load(execution_id)
            return OrchestrationResult(execution_id, state.status, report)
        return self.execute(plan, entries, execution_id=execution_id, resume=True, source=source)
