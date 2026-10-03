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


def omar_close_and_learn(
    response: Apokrisis,
    *,
    biblia_root: Any,
    registry_path: Any = None,
    cronicas_sink: Any = None,
    scope_hint: str | None = None,
    explicit_durable_instruction: bool = False,
    repeated_correction: bool = False,
    stable_workflow: bool = False,
    locked_asset: bool = False,
    active_campaign: bool = False,
    existing_rule_candidates: tuple[str, ...] = (),
    conflict: bool = False,
    supersede: bool = False,
    auto_write: bool = True,
    record_response_event: bool = True,
):
    """OMAR entrypoint: close ANGEL work, evaluate learning, and persist eligible knowledge."""
    from pathlib import Path
    from .cronicas import cronicas_emit_apokrisis
    from .holy_ghost import prepare_learning_cycle, persist_learning_cycle
    from .biblia import retrieve_biblia

    root = Path(biblia_root)
    event = cronicas_emit_apokrisis(response, cronicas_sink) if record_response_event else None

    # First pass resolves the canonical SANPEDRO destination without assuming a file.
    cycle = prepare_learning_cycle(
        response,
        "",
        registry_path=registry_path,
        scope_hint=scope_hint,
        explicit_durable_instruction=explicit_durable_instruction,
        repeated_correction=repeated_correction,
        stable_workflow=stable_workflow,
        locked_asset=locked_asset,
        active_campaign=active_campaign,
        existing_rule_candidates=existing_rule_candidates,
        conflict=conflict,
        supersede=supersede,
    )
    if not cycle.destination.ready_for_review or not cycle.destination.destination_ref:
        return event, cycle

    root_resolved = root.resolve()
    target = (root / cycle.destination.destination_ref).resolve()
    if root_resolved not in target.parents and target != root_resolved:
        raise ValueError("BIBLIA_DESTINATION_OUTSIDE_ROOT")
    if not target.is_file():
        return event, cycle

    # Re-evaluate only against SANPEDRO-authorized BIBLIA for this business.
    authorized = retrieve_biblia(
        response.business_id,
        root=root,
        registry_path=registry_path,
    )
    cycle = prepare_learning_cycle(
        response,
        authorized.text,
        registry_path=registry_path,
        scope_hint=scope_hint,
        explicit_durable_instruction=explicit_durable_instruction,
        repeated_correction=repeated_correction,
        stable_workflow=stable_workflow,
        locked_asset=locked_asset,
        active_campaign=active_campaign,
        existing_rule_candidates=existing_rule_candidates,
        conflict=conflict,
        supersede=supersede,
    )
    if auto_write:
        cycle = persist_learning_cycle(cycle, target, cronicas_sink=cronicas_sink)
    return event, cycle
