"""File-backed persistence adapters for CRONICAS and correction fingerprints.

These adapters are local/runtime primitives. Production storage is intentionally
not selected here.
"""
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .correction_memory import correction_fingerprint
from .cronicas import CronicaEvent


class CronicasJsonlSink:
    """Append privacy-bounded CRONICAS events as JSON Lines."""
    def __init__(self,path: Path):
        self.path=Path(path)

    def __call__(self,event: CronicaEvent)->None:
        if not isinstance(event,CronicaEvent):
            raise TypeError("CRONICAS_EVENT_REQUIRED")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event),ensure_ascii=False,sort_keys=True)+"\n")


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
        return {str(k):int(v) for k,v in raw.items()}

    def _save(self,data: dict[str,int])->None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(self.path.suffix+".tmp")
        temp.write_text(json.dumps(data,sort_keys=True),encoding="utf-8")
        temp.replace(self.path)

    @staticmethod
    def _key(business_id: str,correction: str)->str:
        if not business_id:
            raise ValueError("BUSINESS_ID_REQUIRED")
        if not isinstance(correction,str) or not correction.strip():
            raise ValueError("CORRECTION_REQUIRED")
        return business_id+":"+correction_fingerprint(correction)

    def observe(self,business_id: str,correction: str)->int:
        key=self._key(business_id,correction)
        data=self._load()
        data[key]=data.get(key,0)+1
        self._save(data)
        return data[key]

    def count(self,business_id: str,correction: str)->int:
        return self._load().get(self._key(business_id,correction),0)
