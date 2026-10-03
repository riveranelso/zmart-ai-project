"""APOKRISIS: structured response returned by an ANGEL after bounded work."""
from dataclasses import asdict, dataclass
from typing import Any, Literal

ApokrisisStatus = Literal["SUCCESS", "PARTIAL", "FAILED", "NEEDS_REVIEW"]

@dataclass(frozen=True)
class Apokrisis:
    angel_id: str
    mission_id: str
    status: ApokrisisStatus
    summary: str
    business_id: str
    correlation_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    correction_signals: tuple[str, ...] = ()
    output_ref: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def apokrisis(
    *,
    angel_id: str,
    mission_id: str,
    status: ApokrisisStatus,
    summary: str,
    business_id: str,
    correlation_id: str | None = None,
    evidence_refs: tuple[str, ...] = (),
    uncertainty: tuple[str, ...] = (),
    correction_signals: tuple[str, ...] = (),
    output_ref: str | None = None,
    error_code: str | None = None,
) -> Apokrisis:
    if status not in {"SUCCESS", "PARTIAL", "FAILED", "NEEDS_REVIEW"}:
        raise ValueError("INVALID_APOKRISIS_STATUS")
    if not angel_id or not mission_id or not business_id:
        raise ValueError("APOKRISIS_IDENTITY_REQUIRED")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("APOKRISIS_SUMMARY_REQUIRED")
    if status == "FAILED" and not error_code:
        raise ValueError("APOKRISIS_ERROR_CODE_REQUIRED")
    return Apokrisis(
        angel_id=angel_id,
        mission_id=mission_id,
        status=status,
        summary=summary.strip(),
        business_id=business_id,
        correlation_id=correlation_id,
        evidence_refs=tuple(evidence_refs),
        uncertainty=tuple(uncertainty),
        correction_signals=tuple(correction_signals),
        output_ref=output_ref,
        error_code=error_code,
    )

def close_apokrisis(response: Apokrisis, cronicas_sink=None):
    """Close an ANGEL response into CRONICAS and HOLY GHOST review evidence."""
    from .cronicas import cronicas_emit_apokrisis
    from .holy_ghost import holy_ghost_receive
    event = cronicas_emit_apokrisis(response, cronicas_sink)
    learning = holy_ghost_receive(response)
    return event, learning
