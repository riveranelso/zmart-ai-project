"""HOLY GHOST learning signals derived from completed ANGEL work."""
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from .registry import SanPedroError, sanpedro_resolve

@dataclass(frozen=True)
class LearningSignal:
    mission_id: str
    angel_id: str
    business_id: str
    correlation_id: str | None
    needs_learning_review: bool
    uncertainty: tuple[str, ...]
    correction_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def holy_ghost_receive(response: Any) -> LearningSignal:
    """Create review evidence only. This function never mutates BIBLIA."""
    uncertainty = tuple(response.uncertainty)
    corrections = tuple(response.correction_signals)
    return LearningSignal(
        mission_id=str(response.mission_id),
        angel_id=str(response.angel_id),
        business_id=str(response.business_id),
        correlation_id=response.correlation_id,
        needs_learning_review=bool(uncertainty or corrections),
        uncertainty=uncertainty,
        correction_signals=corrections,
    )

LEARNING_SCOPES=("TEMPORARY","CAMPAIGN","PROJECT","BRAND","WORKFLOW","GLOBAL")

@dataclass(frozen=True)
class LearningProposal:
    mission_id: str
    business_id: str
    scope: str
    reusable: bool
    reason: str
    correction_signals: tuple[str, ...]
    uncertainty: tuple[str, ...]
    requires_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def evaluate_learning(
    signal: LearningSignal,
    *,
    scope_hint: str | None = None,
    explicit_durable_instruction: bool = False,
    repeated_correction: bool = False,
    stable_workflow: bool = False,
    locked_asset: bool = False,
    active_campaign: bool = False,
) -> LearningProposal:
    """Classify learning evidence without mutating BIBLIA."""
    if not signal.needs_learning_review:
        return LearningProposal(signal.mission_id, signal.business_id, "TEMPORARY", False,
                                "NO_LEARNING_SIGNAL", signal.correction_signals,
                                signal.uncertainty, False)
    if scope_hint is not None:
        normalized=scope_hint.upper()
        if normalized not in LEARNING_SCOPES:
            raise ValueError("INVALID_LEARNING_SCOPE")
        scope=normalized
        reason="EXPLICIT_SCOPE_HINT"
    elif locked_asset:
        scope,reason="BRAND","LOCKED_ASSET_RULE"
    elif active_campaign:
        scope,reason="CAMPAIGN","ACTIVE_CAMPAIGN_CONTEXT"
    elif stable_workflow:
        scope,reason="WORKFLOW","STABLE_WORKFLOW"
    elif repeated_correction:
        scope,reason="WORKFLOW","REPEATED_CORRECTION"
    elif explicit_durable_instruction:
        scope,reason="GLOBAL","EXPLICIT_DURABLE_INSTRUCTION"
    else:
        scope,reason="TEMPORARY","INSUFFICIENT_DURABILITY_EVIDENCE"
    reusable=scope!="TEMPORARY"
    return LearningProposal(signal.mission_id, signal.business_id, scope, reusable, reason,
                            signal.correction_signals, signal.uncertainty, True)

SCOPE_DESTINATION_NAMES={
    "GLOBAL":"GLOBAL.md",
    "WORKFLOW":"WORKFLOWS.md",
    "BRAND":"BRANDS.md",
    "PROJECT":"PROJECTS.md",
    "CAMPAIGN":"ACTIVE_CONTEXT.md",
}

@dataclass(frozen=True)
class LearningDestination:
    mission_id: str
    business_id: str
    scope: str
    destination_ref: str | None
    ready_for_review: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def resolve_learning_destination(
    proposal: LearningProposal,
    registry_path: Path | None = None,
) -> LearningDestination:
    """Resolve the narrowest registered BIBLIA destination through SANPEDRO."""
    if not proposal.reusable or proposal.scope == "TEMPORARY":
        return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                                   None, False, "TEMPORARY_NOT_CANONICAL")
    try:
        context=sanpedro_resolve(proposal.business_id, registry_path)
    except SanPedroError as exc:
        return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                                   None, False, str(exc))
    filename=SCOPE_DESTINATION_NAMES.get(proposal.scope)
    if filename is None:
        return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                                   None, False, "DESTINATION_SCOPE_UNSUPPORTED")
    matches=tuple(ref for ref in context.context_refs if ref.endswith("/"+filename) or ref.endswith(filename))
    if not matches:
        return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                                   None, False, "DESTINATION_NOT_REGISTERED")
    return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                               matches[0], True, "DESTINATION_RESOLVED")
