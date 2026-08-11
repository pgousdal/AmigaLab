"""Supervised, manually invoked FS-UAE appliance sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import threading
from typing import Any, TextIO

from .profiles import Asset, PreflightResult, Profile, READ_ONLY_ZONES, preflight, render_fs_uae


SESSION_SCHEMA_VERSION = 1
EMULATOR_LOG_LIMIT = 1024 * 1024
ACTIVE_STATES = {"preparing", "ready", "running"}
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VALID_TRANSITIONS = {
    "preparing": {"ready", "failed"},
    "ready": {"running", "failed"},
    "running": {"exited", "failed", "interrupted"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{os.getpid()}-{secrets.token_hex(3)}"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    temporary.replace(path)


@dataclass(frozen=True)
class SessionState:
    schema_version: int
    session_id: str
    profile_id: str
    profile_schema_version: int
    created_at: str
    started_at: str | None
    ended_at: str | None
    state: str
    runtime_root: str
    config_path: str
    pid: int | None
    launch_argv: tuple[str, ...]
    exit_code: int | None
    termination_reason: str | None
    abnormal_exit: bool
    preflight_launchable: bool
    preflight_path: str
    lifecycle_log: str
    emulator_log: str
    cleanup_status: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["launch_argv"] = list(self.launch_argv)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SessionState":
        data = dict(value)
        data["launch_argv"] = tuple(data.get("launch_argv", ()))
        return cls(**data)


class SessionConflict(RuntimeError):
    pass


class SessionStore:
    def __init__(self, runtime_root: Path):
        self.root = runtime_root.resolve(strict=False)
        self.sessions = self.root / "sessions"
        self.lock_path = self.root / "appliance.lock"

    def session_dir(self, session_id: str) -> Path:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("invalid appliance session ID")
        return self.sessions / session_id

    def save(self, state: SessionState) -> None:
        _atomic_json(self.session_dir(state.session_id) / "state.json", state.to_dict())

    def load(self, session_id: str) -> SessionState:
        return SessionState.from_dict(json.loads((self.session_dir(session_id) / "state.json").read_text(encoding="utf-8")))

    def transition(self, state: SessionState, new_state: str, **changes: Any) -> SessionState:
        if new_state not in VALID_TRANSITIONS.get(state.state, set()):
            raise ValueError(f"invalid appliance session transition: {state.state} -> {new_state}")
        updated = replace(state, state=new_state, **changes)
        self.save(updated)
        return updated

    def list(self) -> tuple[SessionState, ...]:
        result = []
        for path in sorted(self.sessions.glob("*/state.json")) if self.sessions.is_dir() else ():
            try:
                result.append(SessionState.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return tuple(result)

    def lock_status(self) -> dict[str, Any]:
        if not self.lock_path.exists():
            return {"status": "none", "metadata": None}
        metadata = None
        try:
            metadata = json.loads(self.lock_path.read_text(encoding="utf-8") or "null")
        except (OSError, json.JSONDecodeError):
            pass
        # Status inspection must remain read-only. A non-blocking shared lock
        # still conflicts with the supervisor's exclusive lock and therefore
        # distinguishes active from stale metadata without opening for write.
        with self.lock_path.open("r", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "active", "metadata": metadata}
            return {"status": "stale" if metadata else "none", "metadata": metadata}

    def acquire(self, session_id: str) -> TextIO:
        self.session_dir(session_id)  # Validate before touching the lock.
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise SessionConflict("another appliance session holds the runtime lock")
        lock.seek(0)
        lock.truncate()
        json.dump({"schema_version": 1, "session_id": session_id, "supervisor_pid": os.getpid(), "acquired_at": _now()}, lock, sort_keys=True)
        lock.write("\n")
        lock.flush()
        os.fsync(lock.fileno())
        return lock


def _event(log: TextIO, event: str, **details: Any) -> None:
    log.write(json.dumps({"at": _now(), "event": event, **details}, sort_keys=True) + "\n")
    log.flush()


def _capture_output(source: Any, target: Any) -> None:
    written = 0
    truncated = False
    for block in iter(lambda: source.read(65536), b""):
        remaining = EMULATOR_LOG_LIMIT - written
        if remaining > 0:
            target.write(block[:remaining])
            target.flush()
            written += min(len(block), remaining)
        if len(block) > remaining:
            truncated = True
    if truncated:
        target.write(b"\n[AmigaLab: emulator console log truncated at 1048576 bytes]\n")
        target.flush()


def _runtime_is_safe(root: Path, assets: dict[str, Asset]) -> bool:
    resolved = root.resolve(strict=False)
    for asset in assets.values():
        if asset.trust_zone in READ_ONLY_ZONES and asset.path.is_dir():
            try:
                resolved.relative_to(asset.path.resolve(strict=False))
                return False
            except ValueError:
                pass
    return True


@dataclass(frozen=True)
class SessionPlan:
    session_id: str
    session_dir: Path
    profile: Profile | None
    assets: dict[str, Asset]
    preflight: PreflightResult
    config_path: Path
    state_path: Path
    argv: tuple[str, ...]


def plan_session(profile_path: Path, inventory_path: Path, runtime_root: Path, executable: str, session_id: str | None = None) -> SessionPlan:
    session_id = session_id or new_session_id()
    directory = runtime_root.resolve(strict=False) / "sessions" / session_id
    profile, assets, result = preflight(profile_path, inventory_path, directory)
    config = Path(result.config_path) if result.config_path else directory / "config" / "invalid.fs-uae"
    state = Path(result.runtime_path)
    argv = (executable, str(config))
    return SessionPlan(session_id, directory, profile, assets, result, config, state, argv)


def launch_session(plan: SessionPlan, runtime_root: Path, terminate_timeout: float = 5.0) -> SessionState:
    if not plan.preflight.launchable or plan.profile is None:
        raise ValueError("preflight failed; session was not created")
    if not _runtime_is_safe(plan.session_dir, plan.assets):
        raise ValueError("session runtime may not be created inside a read-only preservation zone")
    store = SessionStore(runtime_root)
    lock = store.acquire(plan.session_id)
    child: subprocess.Popen[bytes] | None = None
    directory = plan.session_dir
    logs = directory / "logs"
    lifecycle_path = logs / "lifecycle.jsonl"
    emulator_path = logs / "fs-uae.log"
    created = _now()
    state = SessionState(SESSION_SCHEMA_VERSION, plan.session_id, plan.profile.id, plan.profile.schema_version,
                         created, None, None, "preparing", str(directory), str(plan.config_path), None,
                         plan.argv, None, None, False, True, str(directory / "preflight.json"),
                         str(lifecycle_path), str(emulator_path), "pending")
    try:
        logs.mkdir(parents=True)
        (directory / "overlays").mkdir()
        (directory / "temp").mkdir()
        plan.config_path.parent.mkdir(parents=True)
        plan.state_path.mkdir(parents=True)
        store.save(state)
        _atomic_json(directory / "preflight.json", plan.preflight.to_dict())
        with lifecycle_path.open("a", encoding="utf-8") as lifecycle, emulator_path.open("ab") as emulator:
            _event(lifecycle, "session-created", config_path=str(plan.config_path), argv=list(plan.argv))
            plan.config_path.write_text(render_fs_uae(plan.profile, plan.assets, plan.state_path), encoding="utf-8")
            state = store.transition(state, "ready")
            _event(lifecycle, "configuration-rendered")
            child = subprocess.Popen(list(plan.argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
            capture = threading.Thread(target=_capture_output, args=(child.stdout, emulator), daemon=True)
            capture.start()
            state = store.transition(state, "running", pid=child.pid, started_at=_now())
            _event(lifecycle, "emulator-started", pid=child.pid)
            previous_term = None
            if threading.current_thread() is threading.main_thread():
                previous_term = signal.getsignal(signal.SIGTERM)

                def _termination_request(signum: int, frame: Any) -> None:
                    raise KeyboardInterrupt

                signal.signal(signal.SIGTERM, _termination_request)
            try:
                try:
                    code = child.wait()
                    normal = code == 0
                    state = store.transition(state, "exited" if normal else "failed", ended_at=_now(), pid=None,
                                             exit_code=code, termination_reason="normal-exit" if normal else "non-zero-exit",
                                             abnormal_exit=not normal, cleanup_status="complete")
                except KeyboardInterrupt:
                    _event(lifecycle, "interrupt-received", pid=child.pid)
                    child.terminate()
                    try:
                        code = child.wait(timeout=terminate_timeout)
                        reason = "operator-interrupt"
                    except subprocess.TimeoutExpired:
                        child.kill()
                        code = child.wait()
                        reason = "operator-interrupt-forced-after-timeout"
                    state = store.transition(state, "interrupted", ended_at=_now(), pid=None, exit_code=code,
                                             termination_reason=reason, abnormal_exit=True, cleanup_status="complete")
            finally:
                if previous_term is not None:
                    signal.signal(signal.SIGTERM, previous_term)
                capture.join(timeout=terminate_timeout)
            _event(lifecycle, "session-ended", state=state.state, exit_code=state.exit_code, reason=state.termination_reason)
            return state
    except Exception as error:
        if child is not None and child.poll() is None:
            child.terminate()
        if state.state in {"preparing", "ready", "running"}:
            state = store.transition(state, "failed", ended_at=_now(), pid=None,
                                     exit_code=child.poll() if child else None, termination_reason=f"supervisor-error: {type(error).__name__}",
                                     abnormal_exit=True, cleanup_status="complete")
        raise
    finally:
        if state.state in {"exited", "failed", "interrupted"}:
            lock.seek(0)
            lock.truncate()
            lock.flush()
            os.fsync(lock.fileno())
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def session_status(runtime_root: Path) -> dict[str, Any]:
    store = SessionStore(runtime_root)
    lock = store.lock_status()
    sessions = store.list()
    recent = sessions[-1].to_dict() if sessions else None
    return {"lock": lock, "active_session": lock.get("metadata", {}).get("session_id") if lock["status"] == "active" and lock.get("metadata") else None,
            "stale_or_incomplete": lock["status"] == "stale" or bool(recent and recent["state"] in ACTIVE_STATES and lock["status"] != "active"),
            "most_recent_session": recent}
