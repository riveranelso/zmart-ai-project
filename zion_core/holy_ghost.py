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
    matches=tuple(ref for ref in context.context_refs if Path(ref).name == filename)
    if not matches:
        return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                                   None, False, "DESTINATION_NOT_REGISTERED")
    if len(matches) != 1:
        return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                                   None, False, "DESTINATION_AMBIGUOUS")
    return LearningDestination(proposal.mission_id, proposal.business_id, proposal.scope,
                               matches[0], True, "DESTINATION_RESOLVED")

PROMOTION_ACTIONS=("ADD","UPDATE","SUPERSEDE","NO_CHANGE","CONFLICT","NOT_READY")

@dataclass(frozen=True)
class PromotionDecision:
    mission_id: str
    business_id: str
    scope: str
    destination_ref: str | None
    action: str
    proposed_rules: tuple[str, ...]
    matched_rules: tuple[str, ...]
    reason: str
    requires_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _normalize_rule(value: str) -> str:
    return " ".join(value.strip().lower().split())

def propose_biblia_promotion(
    proposal: LearningProposal,
    destination: LearningDestination,
    existing_text: str,
    *,
    existing_rule_candidates: tuple[str, ...] = (),
    conflict: bool = False,
    supersede: bool = False,
) -> PromotionDecision:
    """Produce a deterministic BIBLIA promotion decision without writing files."""
    if not destination.ready_for_review or not destination.destination_ref:
        return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                 destination.destination_ref, "NOT_READY", (), (),
                                 destination.reason, False)
    rules=tuple(x.strip() for x in proposal.correction_signals if isinstance(x,str) and x.strip())
    if not rules:
        return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                 destination.destination_ref, "NO_CHANGE", (), (),
                                 "NO_CORRECTION_RULES", False)
    if conflict:
        return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                 destination.destination_ref, "CONFLICT", rules,
                                 tuple(existing_rule_candidates), "EXPLICIT_CONFLICT", True)
    normalized_text=_normalize_rule(existing_text)
    exact=tuple(rule for rule in rules if _normalize_rule(rule) in normalized_text)
    if len(exact)==len(rules):
        return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                 destination.destination_ref, "NO_CHANGE", rules, exact,
                                 "RULE_ALREADY_PRESENT", False)
    candidates=tuple(x.strip() for x in existing_rule_candidates if isinstance(x,str) and x.strip())
    missing_candidates=tuple(x for x in candidates if _normalize_rule(x) not in normalized_text)
    if missing_candidates:
        return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                 destination.destination_ref, "CONFLICT", rules, candidates,
                                 "CANDIDATE_OUTSIDE_AUTHORIZED_CONTEXT", True)
    if supersede:
        if not candidates:
            return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                     destination.destination_ref, "CONFLICT", rules, (),
                                     "SUPERSESSION_CANDIDATE_REQUIRED", True)
        if len(candidates)!=len(rules):
            return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                     destination.destination_ref, "CONFLICT", rules, candidates,
                                     "SUPERSESSION_RULE_COUNT_MISMATCH", True)
        return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                 destination.destination_ref, "SUPERSEDE", rules, candidates,
                                 "EXPLICIT_SUPERSESSION", True)
    if candidates:
        return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                                 destination.destination_ref, "UPDATE", rules, candidates,
                                 "EXISTING_RULE_CANDIDATE", True)
    return PromotionDecision(proposal.mission_id, proposal.business_id, proposal.scope,
                             destination.destination_ref, "ADD", rules, (),
                             "NEW_RULE", True)


@dataclass(frozen=True)
class LearningCycle:
    signal: Any
    proposal: LearningProposal
    destination: LearningDestination
    promotion: PromotionDecision
    grapho: Any = None

def prepare_learning_cycle(
    response: Any,
    existing_text: str = "",
    *,
    registry_path: Path | None = None,
    scope_hint: str | None = None,
    explicit_durable_instruction: bool = False,
    repeated_correction: bool = False,
    stable_workflow: bool = False,
    locked_asset: bool = False,
    active_campaign: bool = False,
    existing_rule_candidates: tuple[str, ...] = (),
    conflict: bool = False,
    supersede: bool = False,
) -> LearningCycle:
    """Prepare the complete learning decision before persistence."""
    signal=holy_ghost_receive(response)
    proposal=evaluate_learning(
        signal,
        scope_hint=scope_hint,
        explicit_durable_instruction=explicit_durable_instruction,
        repeated_correction=repeated_correction,
        stable_workflow=stable_workflow,
        locked_asset=locked_asset,
        active_campaign=active_campaign,
    )
    destination=resolve_learning_destination(proposal,registry_path)
    promotion=propose_biblia_promotion(
        proposal,destination,existing_text,
        existing_rule_candidates=existing_rule_candidates,
        conflict=conflict,
        supersede=supersede,
    )
    return LearningCycle(signal,proposal,destination,promotion,None)


def persist_learning_cycle(
    cycle: LearningCycle,
    path: Path,
    *,
    cronicas_sink: Any = None,
    origin_angel_id: str | None = None,
    correlation_id: str | None = None,
) -> LearningCycle:
    """Persist an eligible prepared cycle through GRAPHO."""
    if cycle.promotion.action not in {"ADD","UPDATE","SUPERSEDE"}:
        return cycle
    from .grapho import grapho_write
    result=grapho_write(path,cycle.promotion,cronicas_sink,origin_angel_id=origin_angel_id,correlation_id=correlation_id)
    return LearningCycle(cycle.signal,cycle.proposal,cycle.destination,cycle.promotion,result)
