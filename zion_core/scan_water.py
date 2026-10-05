"""SCAN Water Intelligence ZIP-resolution contract for ZION batch work.

This is a product adapter, not a second runtime. It defines what one SCAN ZIP
item means and validates resolver output before it can be reused downstream.
"""
from dataclasses import dataclass
import re
from typing import Iterable

from .batch import BatchPlan, plan_batch

SCAN_BUSINESS_ID="scan-water-intelligence"
SCAN_ZIP_INTENT="resolve_water_system_zip"
RESOLVED="RESOLVED"
NEEDS_MORE_LOCATION="NEEDS_MORE_LOCATION"
NO_ACTIVE_CWS="NO_ACTIVE_CWS"
REVIEW_REQUIRED="REVIEW_REQUIRED"
SCAN_ZIP_STATUSES=(RESOLVED,NEEDS_MORE_LOCATION,NO_ACTIVE_CWS,REVIEW_REQUIRED)

_ZIP=re.compile(r"^\d{5}$")
_PWSID=re.compile(r"^[A-Z]{2}\d{7}$")


@dataclass(frozen=True)
class ScanZipResult:
    zip_code: str
    status: str
    pwsid: str | None
    confidence: float
    evidence_refs: tuple[str, ...]
    reason: str


def normalize_zip(value: str) -> str:
    if not isinstance(value,str):
        raise ValueError("SCAN_ZIP_INVALID")
    value=value.strip()
    if not _ZIP.fullmatch(value):
        raise ValueError("SCAN_ZIP_INVALID")
    return value


def plan_scan_zip_batch(
    zip_codes: Iterable[str],
    *,
    batch_id: str,
    requested_by: str = "OMAR",
    limit_hint: int = 25,
) -> BatchPlan:
    """Create the canonical SCAN ZIP batch without embedding lookup results."""
    if not isinstance(limit_hint,int) or isinstance(limit_hint,bool) or limit_hint < 1:
        raise ValueError("SCAN_BATCH_LIMIT_INVALID")
    normalized=tuple(normalize_zip(value) for value in zip_codes)
    return plan_batch(
        batch_id=batch_id,
        business_id=SCAN_BUSINESS_ID,
        intent=SCAN_ZIP_INTENT,
        requested_by=requested_by,
        scope="WORKFLOW",
        item_keys=normalized,
        mission_defaults={"risk_level":"LOW","angel_count_max":1},
    )


def validate_scan_zip_result(
    *,
    zip_code: str,
    status: str,
    pwsid: str | None,
    confidence: float,
    evidence_refs: Iterable[str],
    reason: str,
) -> ScanZipResult:
    zip_code=normalize_zip(zip_code)
    if status not in SCAN_ZIP_STATUSES:
        raise ValueError("SCAN_STATUS_INVALID")
    if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not 0 <= confidence <= 1:
        raise ValueError("SCAN_CONFIDENCE_INVALID")
    if not isinstance(reason,str) or not reason.strip():
        raise ValueError("SCAN_REASON_REQUIRED")
    refs=[]
    for ref in evidence_refs:
        if not isinstance(ref,str) or not ref.strip() or ref != ref.strip():
            raise ValueError("SCAN_EVIDENCE_INVALID")
        if ref not in refs:
            refs.append(ref)
    if status == RESOLVED:
        if not isinstance(pwsid,str) or not _PWSID.fullmatch(pwsid):
            raise ValueError("SCAN_RESOLVED_PWSID_REQUIRED")
        if not refs:
            raise ValueError("SCAN_RESOLVED_EVIDENCE_REQUIRED")
    elif pwsid is not None:
        raise ValueError("SCAN_UNRESOLVED_PWSID_FORBIDDEN")
    return ScanZipResult(
        zip_code=zip_code,status=status,pwsid=pwsid,
        confidence=float(confidence),evidence_refs=tuple(refs),reason=reason.strip(),
    )
