"""File-backed persistence adapters for CRONICAS and correction fingerprints.

These adapters are local/runtime primitives. Production storage is intentionally
not selected here.
"""
from dataclasses import asdict
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .correction_memory import correction_fingerprint
from .cronicas import CronicaEvent


def _operation_digest(business_id: str,operation: str,identity: str)->str:
    """Stable local lock identity; not a durable pre-action claim."""
    parts=(business_id,operation,identity)
    if not all(isinstance(x,str) and x.strip() for x in parts):
        raise ValueError("ATOMIC_CLAIM_IDENTITY_REQUIRED")
    raw="\x1f".join(x.strip() for x in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class LocalOperationLock:
    """Short-lived local lock for an idempotency critical section.

    Lock metadata identifies the owning local process. A contender may recover
    a lock only when the recorded PID can be proven dead. Unknown ownership
    fails closed by timeout. CRONICAS remains the durable business record.
    """
    def __init__(self,root: Path,*,poll_seconds: float=0.01,timeout_seconds: float=5.0):
        self.root=Path(root)
        self.poll_seconds=poll_seconds
        self.timeout_seconds=timeout_seconds

    @staticmethod
    def _owner_alive(pid: int)->bool | None:
        if not isinstance(pid,int) or pid <= 0:
            return None
        try:
            os.kill(pid,0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return None
        return True

    @staticmethod
    def _process_start_identity(pid: int)->str | None:
        if not isinstance(pid,int) or pid <= 0:
            return None
        stat=Path(f"/proc/{pid}/stat")
        try:
            raw=stat.read_text(encoding="utf-8")
        except OSError:
            return None
        # /proc/<pid>/stat field 2 is parenthesized and may contain spaces.
        close=raw.rfind(")")
        if close < 0:
            return None
        fields=raw[close+2:].split()
        # starttime is field 22 overall, index 19 after fields 1-2 are removed.
        if len(fields) <= 19:
            return None
        return fields[19]

    @staticmethod
    def _read_owner(path: Path)->dict[str,Any] | None:
        try:
            raw=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):
            return None
        return raw if isinstance(raw,dict) else None

    def _recover_dead_owner(self,path: Path)->bool:
        owner=self._read_owner(path)
        if not owner:
            return False
        pid=owner.get("pid")
        alive=self._owner_alive(pid)
        if alive is True:
            recorded_start=owner.get("process_start")
            current_start=self._process_start_identity(pid)
            if not (recorded_start and current_start and recorded_start != current_start):
                return False
        elif alive is not False:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        else:
            try:
                dir_fd=os.open(path.parent,os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                # The dead-owner lock is already removed. Recovery is
                # logically complete even if directory metadata sync fails.
                pass
        return True

    @contextmanager
    def hold(self,business_id: str,operation: str,identity: str):
        digest=_operation_digest(business_id,operation,identity)
        self.root.mkdir(parents=True,exist_ok=True)
        path=self.root/(digest+".lock")
        deadline=time.monotonic()+self.timeout_seconds
        fd=None
        while fd is None:
            try:
                fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            except FileExistsError:
                if self._recover_dead_owner(path):
                    continue
                if time.monotonic()>=deadline:
                    raise TimeoutError("IDEMPOTENCY_LOCK_TIMEOUT")
                time.sleep(self.poll_seconds)
        try:
            pid=os.getpid()
            payload={"pid":pid,"process_start":self._process_start_identity(pid),
                     "business_id":business_id.strip(),"operation":operation.strip(),
                     "identity":identity.strip()}
            encoded=json.dumps(payload,sort_keys=True).encode("utf-8")
            offset=0
            while offset < len(encoded):
                written=os.write(fd,encoded[offset:])
                if not isinstance(written,int) or written <= 0:
                    raise OSError("LOCK_OWNER_METADATA_SHORT_WRITE")
                offset+=written
            os.fsync(fd)
            yield
        finally:
            os.close(fd)
            # If ownership publication failed before the protected section was
            # entered, this process still owns the O_EXCL file and must remove
            # it; otherwise malformed/empty metadata would fail closed forever.
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            else:
                try:
                    dir_fd=os.open(self.root,os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except OSError:
                    # The coordination lock is already removed. Do not turn
                    # completed protected work into a false retryable failure.
                    pass


class CronicasJsonlSink:
    """Append privacy-bounded CRONICAS events as serialized JSON Lines."""
    def __init__(self,path: Path):
        self.path=Path(path)

    def __call__(self,event: CronicaEvent)->None:
        if not isinstance(event,CronicaEvent):
            raise TypeError("CRONICAS_EVENT_REQUIRED")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        lock=LocalOperationLock(self.path.parent/(self.path.name+".append-locks"))
        with lock.hold("CRONICAS","JSONL_APPEND",str(self.path.resolve())):
            payload=json.dumps(asdict(event),ensure_ascii=False,sort_keys=True)+"\n"
            with self.path.open("a",encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())


class PersistentCorrectionMemory:
    """Persist only business-scoped correction fingerprints and counts."""
    def __init__(self,path: Path):
        self.path=Path(path)

    def _load(self)->dict[str,int]:
        if not self.path.is_file():
            return {}
        raw=json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw,dict):
            raise ValueError("INVALID_CORRECTION_MEMORY")
        data={}
        for key,value in raw.items():
            if (not isinstance(key,str) or not key or not isinstance(value,int)
                    or isinstance(value,bool) or value < 0):
                raise ValueError("INVALID_CORRECTION_MEMORY")
            data[key]=value
        return data

    def _save(self,data: dict[str,int])->None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(self.path.suffix+".tmp")
        with temp.open("w",encoding="utf-8") as handle:
            handle.write(json.dumps(data,sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.path)
        try:
            dir_fd=os.open(self.path.parent,os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # The atomic replacement is already logically committed. A
            # directory-sync failure must not turn success into a retry that
            # increments the same correction again.
            pass

    @staticmethod
    def _key(business_id: str,correction: str)->str:
        if (not isinstance(business_id,str) or not business_id.strip()
                or business_id != business_id.strip()):
            raise ValueError("BUSINESS_ID_REQUIRED")
        if not isinstance(correction,str) or not correction.strip():
            raise ValueError("CORRECTION_REQUIRED")
        return business_id+":"+correction_fingerprint(correction)

    def observe(self,business_id: str,correction: str)->int:
        key=self._key(business_id,correction)
        lock=LocalOperationLock(self.path.parent/(self.path.name+".locks"))
        with lock.hold(business_id,"CORRECTION_MEMORY",correction_fingerprint(correction)):
            data=self._load()
            data[key]=data.get(key,0)+1
            self._save(data)
            return data[key]

    def count(self,business_id: str,correction: str)->int:
        key=self._key(business_id,correction)
        lock=LocalOperationLock(self.path.parent/(self.path.name+".locks"))
        with lock.hold(business_id,"CORRECTION_MEMORY",correction_fingerprint(correction)):
            return self._load().get(key,0)


class CronicasReadError(ValueError):
    """Raised when persisted CRONICAS cannot be safely decoded."""


def read_cronicas(
    path: Path,
    *,
    business_id: str | None = None,
    event_type: str | None = None,
    mission_id: str | None = None,
) -> tuple[CronicaEvent, ...]:
    """Read append-only CRONICAS metadata without granting it canonical authority."""
    source=Path(path)
    if not source.is_file():
        return ()
    lock=LocalOperationLock(source.parent/(source.name+".append-locks"))
    with lock.hold("CRONICAS","JSONL_APPEND",str(source.resolve())):
        if not source.is_file():
            return ()
        snapshot=source.read_text(encoding="utf-8")
    events=[]
    for line_number,line in enumerate(snapshot.splitlines(),start=1):
        if not line.strip():
            continue
        try:
            raw=json.loads(line)
            if not isinstance(raw,dict):
                raise TypeError
            for key in ("event_id","occurred_at","event_type","mission_id","action","reason"):
                if not isinstance(raw.get(key),str) or not raw[key].strip():
                    raise TypeError
            for key in ("business_id","command","host","denied_by","correlation_id","status","dispatch_fingerprint","response_fingerprint"):
                value=raw.get(key)
                if value is not None and (not isinstance(value,str) or not value.strip()):
                    raise TypeError
            for fingerprint_key in ("dispatch_fingerprint","response_fingerprint"):
                fingerprint=raw.get(fingerprint_key)
                if fingerprint is not None and (
                    len(fingerprint)!=64 or any(ch not in "0123456789abcdef" for ch in fingerprint)
                ):
                    raise TypeError
            for key in ("angel_ids","evidence_refs"):
                value=raw.get(key,[])
                if not isinstance(value,list) or not all(
                    isinstance(item,str) and item.strip() for item in value
                ):
                    raise TypeError
                raw[key]=tuple(value)
            if raw.get("event_type")=="MISSION_DECISION" and raw.get("action")=="DISPATCH":
                import re
                if raw["angel_ids"] and not all(
                    re.fullmatch(r"[A-Z][A-Z0-9]*\\.HOST-[0-9]{2}\\.ANGEL-[0-9]{3}",item)
                    for item in raw["angel_ids"]
                ):
                    raise TypeError
            for key in ("uncertainty_count","correction_count"):
                value=raw.get(key,0)
                if not isinstance(value,int) or isinstance(value,bool) or value < 0:
                    raise TypeError
            event=CronicaEvent(**raw)
        except (json.JSONDecodeError,TypeError,KeyError,ValueError) as exc:
            raise CronicasReadError(f"INVALID_CRONICAS_LINE:{line_number}") from exc
        if business_id is not None and event.business_id != business_id:
            continue
        if event_type is not None and event.event_type != event_type:
            continue
        if mission_id is not None and event.mission_id != mission_id:
            continue
        events.append(event)
    return tuple(events)
