"""Correction repetition memory for HOLY GHOST learning signals."""
from dataclasses import dataclass, field
import hashlib
import re


def correction_fingerprint(text: str) -> str:
    normalized=re.sub(r"\s+"," ",text.casefold().strip())
    normalized=re.sub(r"[^\w\s]","",normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class CorrectionMemory:
    """Non-persistent repetition memory isolated by business."""
    _counts: dict[tuple[str,str],int] = field(default_factory=dict)

    def observe(self,business_id: str,correction: str) -> int:
        if not business_id:
            raise ValueError("BUSINESS_ID_REQUIRED")
        if not isinstance(correction,str) or not correction.strip():
            raise ValueError("CORRECTION_REQUIRED")
        key=(business_id,correction_fingerprint(correction))
        count=self._counts.get(key,0)+1
        self._counts[key]=count
        return count

    def count(self,business_id: str,correction: str) -> int:
        return self._counts.get((business_id,correction_fingerprint(correction)),0)
