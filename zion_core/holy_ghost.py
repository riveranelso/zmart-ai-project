"""HOLY GHOST learning signals derived from completed ANGEL work."""
from dataclasses import asdict, dataclass
from typing import Any

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
