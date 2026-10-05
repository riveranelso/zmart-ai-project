"""Import existing SCAN ZIP work into the ZION batch boundary."""
from dataclasses import dataclass
from typing import Any, Iterable

from .scan_water import normalize_zip, plan_scan_zip_batch

_NEEDS_MORE_LOCATION={"NEEDS_MORE_LOCATION","needs_more_location"}


@dataclass(frozen=True)
class ScanImportSummary:
    total_rows: int
    unique_zips: int
    selected: tuple[str, ...]
    skipped_resolved: int
    skipped_other: int


def select_scan_needs_more_location(
    rows: Iterable[dict[str, Any]],
    *,
    zip_field: str = "zip_code",
    status_field: str = "status",
) -> ScanImportSummary:
    """Select unresolved ZIPs without reprocessing resolved/other rows."""
    if not isinstance(zip_field,str) or not zip_field.strip():
        raise ValueError("SCAN_IMPORT_ZIP_FIELD_INVALID")
    if not isinstance(status_field,str) or not status_field.strip():
        raise ValueError("SCAN_IMPORT_STATUS_FIELD_INVALID")
    total=resolved=other=0
    seen={}
    selected=[]
    for row in rows:
        total+=1
        if not isinstance(row,dict):
            raise ValueError("SCAN_IMPORT_ROW_INVALID")
        if zip_field not in row or status_field not in row:
            raise ValueError("SCAN_IMPORT_REQUIRED_FIELD_MISSING")
        zip_code=normalize_zip(str(row[zip_field]))
        status=row[status_field]
        if not isinstance(status,str) or not status.strip():
            raise ValueError("SCAN_IMPORT_STATUS_INVALID")
        normalized=status.strip()
        prior=seen.get(zip_code)
        if prior is not None and prior != normalized:
            raise ValueError("SCAN_IMPORT_ZIP_STATUS_CONFLICT")
        if prior is not None:
            continue
        seen[zip_code]=normalized
        if normalized in _NEEDS_MORE_LOCATION:
            selected.append(zip_code)
        elif normalized.upper()=="RESOLVED":
            resolved+=1
        else:
            other+=1
    return ScanImportSummary(total,len(seen),tuple(selected),resolved,other)


def plan_scan_import_batch(
    rows: Iterable[dict[str, Any]],
    *,
    batch_id: str,
    zip_field: str = "zip_code",
    status_field: str = "status",
):
    summary=select_scan_needs_more_location(
        rows,zip_field=zip_field,status_field=status_field,
    )
    plan=plan_scan_zip_batch(summary.selected,batch_id=batch_id)
    return summary,plan
