"""Serial, approval-bound HTTPS mirror execution with resumable staging."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import md5, sha1, sha256, sha512
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import ExternalSource, MirrorPlan
from .storage import ExternalStorage, stable_id


def now() -> str: return datetime.now(timezone.utc).isoformat()


def validate_content_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"archive.org", "www.archive.org"}:
        raise ValueError("content URL must use approved Internet Archive HTTPS")
    try:
        for address in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ValueError("content URL resolves to a private or local address")
    except socket.gaierror:
        # Tests and offline plan validation may not have DNS; hostname policy
        # remains enforced and connection failure is reported by the client.
        pass


@dataclass(frozen=True)
class AcquisitionEntry:
    id: str
    execution_id: str
    plan_id: str
    source_id: str
    item_identifier: str
    upstream_filename: str
    locator: str
    expected_size: int | None
    upstream_hashes: dict[str, str]
    staging_path: str
    final_path: str
    media_category: str
    license_profile: str
    state: str = "pending"
    byte_offset: int = 0
    bytes_downloaded: int = 0
    attempts: int = 0
    http_metadata: dict[str, object] = None
    local_hashes: dict[str, str] = None
    verification_status: str = "not-verified"
    error_category: str = ""
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""


@dataclass(frozen=True)
class MirrorExecution:
    id: str
    plan_id: str
    source_id: str
    snapshot_id: str
    plan_fingerprint: str
    state: str
    started_at: str
    updated_at: str
    entries: tuple[str, ...]
    completed_entries: tuple[str, ...] = ()
    reused_entries: tuple[str, ...] = ()
    skipped_entries: tuple[str, ...] = ()
    blocked_entries: tuple[str, ...] = ()
    failed_entries: tuple[str, ...] = ()
    total_expected_bytes: int = 0
    downloaded_bytes: int = 0
    retry_count: int = 0
    latest_error: str = ""
    resumable: bool = True
    final_result: str = ""
    schema_version: int = 1


class MirrorExecutionStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save_execution(self, execution): return self.storage.put("mirror-executions", execution.id, execution)
    def load_execution(self, execution_id): return MirrorExecution(**self.storage.get("mirror-executions", execution_id))
    def save_entry(self, entry): return self.storage.put("mirror-acquisition-entries", entry.id, entry)
    def load_entry(self, entry_id): return AcquisitionEntry(**self.storage.get("mirror-acquisition-entries", entry_id))
    def list_entries(self, execution_id): return tuple(AcquisitionEntry(**item) for item in self.storage.list("mirror-acquisition-entries") if item.get("execution_id") == execution_id)


class AcquisitionHttpClient:
    def __init__(self, *, timeout: float = 30, user_agent: str = "AmigaLab/2.17", opener=urlopen): self.timeout, self.user_agent, self.opener = timeout, user_agent, opener

    def stream(self, url: str, destination: Path, *, offset: int = 0):
        validate_content_url(url)
        headers = {"User-Agent": self.user_agent, "Accept": "application/octet-stream"}
        if offset: headers["Range"] = f"bytes={offset}-"
        request = Request(url, headers=headers)
        with self.opener(request, timeout=self.timeout) as response:
            final_url = response.geturl()
            validate_content_url(final_url)
            status = getattr(response, "status", 200)
            if offset and status != 206: raise ValueError("server did not honor range resume")
            mode = "ab" if offset else "wb"
            total = offset
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open(mode) as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk); total += len(chunk)
        return {"status": status, "url": final_url, "content_length": total, "content_range": response.headers.get("Content-Range", "")}


def local_hashes(path: Path) -> tuple[dict[str, str], int]:
    digests = (md5(), sha1(), sha256(), sha512()); size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            for digest in digests: digest.update(chunk)
    return {name: digest.hexdigest() for name, digest in zip(("md5", "sha1", "sha256", "sha512"), digests)}, size


def validate_upstream(hashes: dict[str, str], observed: dict[str, str]) -> str:
    checks = [(algorithm, value.lower(), observed.get(algorithm, "").lower()) for algorithm, value in hashes.items() if algorithm in {"md5", "sha1"} and value]
    if any(expected != actual for _, expected, actual in checks): return "mismatched"
    return "matched" if checks else "not-reported"


def deterministic_entry_id(plan_id: str, item: str, filename: str) -> str:
    return stable_id({"plan": plan_id, "item": item, "filename": filename})


def create_execution(plan: MirrorPlan, source: ExternalSource, staging_root: Path, media_root: Path) -> tuple[MirrorExecution, tuple[AcquisitionEntry, ...]]:
    execution_id = stable_id({"plan": plan.id, "fingerprint": plan.fingerprint})
    entries = []
    for selected in plan.selected_files:
        item, filename = str(selected["item"]), str(selected["filename"])
        entry_id = deterministic_entry_id(plan.id, item, filename)
        staging = staging_root / "mirror-executions" / execution_id / entry_id / "content.partial"
        final = media_root / plan.target_category / plan.id / filename
        entries.append(AcquisitionEntry(entry_id, execution_id, plan.id, source.id, item, filename, str(selected.get("locator", "")), selected.get("size"), {key: str(selected[key]) for key in ("md5", "sha1") if selected.get(key)}, str(staging), str(final), plan.target_category, source.license_profile, created_at=now(), updated_at=now(), http_metadata={}, local_hashes={}))
    execution = MirrorExecution(execution_id, plan.id, source.id, plan.snapshot_id, plan.fingerprint, "planned", now(), now(), tuple(entry.id for entry in entries), total_expected_bytes=sum(entry.expected_size or 0 for entry in entries))
    return execution, tuple(entries)


def execute_mirror(plan: MirrorPlan, source: ExternalSource, store: MirrorExecutionStore,
                   staging_root: Path, media_root: Path, *, yes: bool,
                   client: AcquisitionHttpClient | None = None) -> MirrorExecution:
    if not yes: raise PermissionError("mirror execution requires --yes")
    if plan.status != "approved" or not plan.approval_history:
        raise ValueError("mirror plan requires a matching append-only approval event")
    execution, entries = create_execution(plan, source, staging_root, media_root)
    store.save_execution(execution)
    for entry in entries: store.save_entry(entry)
    client = client or AcquisitionHttpClient()
    execution = replace(execution, state="acquiring", updated_at=now())
    store.save_execution(execution)
    for entry in entries:
        current = store.load_entry(entry.id)
        if Path(current.final_path).is_file():
            hashes, size = local_hashes(Path(current.final_path))
            if current.expected_size in (None, size) and (not current.upstream_hashes or validate_upstream(current.upstream_hashes, hashes) == "matched"):
                store.save_entry(replace(current, state="reused", local_hashes=hashes, bytes_downloaded=size, verification_status="matched", updated_at=now(), completed_at=now()))
                execution = replace(execution, reused_entries=tuple((*execution.reused_entries, current.id)), downloaded_bytes=execution.downloaded_bytes + size, updated_at=now())
                store.save_execution(execution); continue
            store.save_entry(replace(current, state="blocked", error_category="destination-conflict", error_message="existing destination differs")); execution = replace(execution, blocked_entries=tuple((*execution.blocked_entries, current.id)), state="blocked", latest_error="destination conflict"); store.save_execution(execution); continue
        try:
            partial = Path(current.staging_path); offset = partial.stat().st_size if partial.exists() else 0
            store.save_entry(replace(current, state="downloading", byte_offset=offset, bytes_downloaded=offset, attempts=current.attempts + 1, updated_at=now()))
            metadata = client.stream(current.locator, partial, offset=offset)
            hashes, size = local_hashes(partial)
            validation = validate_upstream(current.upstream_hashes, hashes)
            if current.expected_size is not None and size != current.expected_size: raise ValueError("downloaded size differs from approved size")
            if validation == "mismatched": raise ValueError("upstream hash mismatch")
            store.save_entry(replace(current, state="ready-to-finalize", bytes_downloaded=size, local_hashes=hashes, http_metadata=metadata, verification_status=validation, updated_at=now()))
            target = Path(current.final_path); target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{execution.id}.partial")
            import shutil
            shutil.copyfile(partial, temporary); temporary.replace(target)
            store.save_entry(replace(current, state="completed", bytes_downloaded=size, local_hashes=hashes, http_metadata=metadata, verification_status=validation, updated_at=now(), completed_at=now()))
            execution = replace(execution, completed_entries=tuple((*execution.completed_entries, current.id)), downloaded_bytes=execution.downloaded_bytes + size, updated_at=now())
            store.save_execution(execution)
            ExternalStorage(store.storage.root).put("mirror-provenance", current.id, {"source_id": source.id, "item_identifier": current.item_identifier, "upstream_filename": current.upstream_filename, "plan_id": plan.id, "execution_id": execution.id, "local_hashes": hashes, "upstream_hashes": current.upstream_hashes, "final_path": str(target)})
        except Exception as error:
            store.save_entry(replace(current, state="failed", error_category="acquisition", error_message=str(error), updated_at=now()))
            execution = replace(execution, state="failed", failed_entries=tuple((*execution.failed_entries, current.id)), latest_error=str(error), updated_at=now())
            store.save_execution(execution); break
    if execution.state not in {"failed", "blocked"}:
        execution = replace(execution, state="completed" if len(execution.completed_entries) + len(execution.reused_entries) == len(entries) else "completed-with-skips", resumable=False, final_result="success", updated_at=now())
        store.save_execution(execution)
    return execution


def resume_mirror(execution: MirrorExecution, plan: MirrorPlan, source: ExternalSource, store: MirrorExecutionStore,
                  staging_root: Path, media_root: Path, *, yes: bool, client: AcquisitionHttpClient | None = None) -> MirrorExecution:
    if not yes: raise PermissionError("mirror resume requires --yes")
    if execution.plan_id != plan.id or execution.plan_fingerprint != plan.fingerprint:
        raise ValueError("mirror execution does not match approved plan fingerprint")
    if execution.state in {"completed", "cancelled"}: return execution
    # Reuse the canonical execution and entries; only pending/failed entries
    # are retried. Completed/reused entries never issue content requests.
    for entry in store.list_entries(execution.id):
        if entry.state in {"completed", "reused", "skipped"}: continue
        current = replace(entry, attempts=entry.attempts + 1, state="downloading", updated_at=now())
        store.save_entry(current)
        try:
            partial = Path(current.staging_path); offset = partial.stat().st_size if partial.exists() else 0
            (client or AcquisitionHttpClient()).stream(current.locator, partial, offset=offset)
            hashes, size = local_hashes(partial)
            if current.expected_size is not None and size != current.expected_size: raise ValueError("downloaded size differs from approved size")
            if validate_upstream(current.upstream_hashes, hashes) == "mismatched": raise ValueError("upstream hash mismatch")
            target = Path(current.final_path); target.parent.mkdir(parents=True, exist_ok=True); temporary = target.with_name(f".{target.name}.{execution.id}.partial")
            import shutil; shutil.copyfile(partial, temporary); temporary.replace(target)
            store.save_entry(replace(current, state="completed", bytes_downloaded=size, local_hashes=hashes, verification_status="matched", updated_at=now(), completed_at=now()))
        except Exception as error:
            store.save_entry(replace(current, state="failed", error_category="acquisition", error_message=str(error), updated_at=now()))
    entries = store.list_entries(execution.id)
    success = all(entry.state in {"completed", "reused", "skipped"} for entry in entries)
    updated = replace(execution, state="completed" if success else "failed", resumable=not success, completed_entries=tuple(entry.id for entry in entries if entry.state == "completed"), failed_entries=tuple(entry.id for entry in entries if entry.state == "failed"), updated_at=now(), final_result="success" if success else "incomplete")
    store.save_execution(updated)
    return updated
