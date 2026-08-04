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

from .models import TransactionEntry
from .services import hash_file, validate_staging, verify_destination


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


class ExecutionStateStore:
    def __init__(self, root: Path):
        self.root = root

    def save(self, state: ExecutionState) -> Path:
        return _atomic_json(self.root / "recovery-executions" / f"{state.execution_id}.json", asdict(state))

    def load(self, execution_id: str) -> ExecutionState:
        data = json.loads((self.root / "recovery-executions" / f"{execution_id}.json").read_text(encoding="utf-8"))
        for key in ("completed_actions", "skipped_actions", "failed_actions", "failures", "persisted_records"):
            data[key] = tuple(data.get(key, ()))
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
