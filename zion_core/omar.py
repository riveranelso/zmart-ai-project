"""OMAR: stable application entrypoints for ZION CORE orchestration."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .apokrisis import Apokrisis, omar_close_and_learn
from .biblia import BibliaContext, retrieve_biblia


@dataclass(frozen=True)
class MissionContext:
    business_id: str
    biblia: BibliaContext

    @property
    def knowledge(self) -> str:
        return self.biblia.text


def prepare_mission(
    business_id: str,
    *,
    biblia_root: Path,
    registry_path: Path | None = None,
) -> MissionContext:
    """Load isolated canonical knowledge before OMAR dispatches a mission."""
    biblia=retrieve_biblia(
        business_id,
        root=biblia_root,
        registry_path=registry_path,
    )
    return MissionContext(business_id=business_id,biblia=biblia)


@dataclass(frozen=True)
class LearningIntent:
    scope_hint: str | None = None
    explicit_durable_instruction: bool = False
    repeated_correction: bool = False
    stable_workflow: bool = False
    locked_asset: bool = False
    active_campaign: bool = False
    existing_rule_candidates: tuple[str, ...] = ()
    conflict: bool = False
    supersede: bool = False
    auto_write: bool = True


def receive_apokrisis(
    response: Apokrisis,
    *,
    biblia_root: Path,
    registry_path: Path | None = None,
    cronicas_sink: Any = None,
    learning: LearningIntent | None = None,
    record_response_event: bool = True,
):
    """Stable OMAR port for closing ANGEL work and running the learning cycle."""
    intent=learning or LearningIntent()
    return omar_close_and_learn(
        response,
        biblia_root=biblia_root,
        registry_path=registry_path,
        cronicas_sink=cronicas_sink,
        scope_hint=intent.scope_hint,
        explicit_durable_instruction=intent.explicit_durable_instruction,
        repeated_correction=intent.repeated_correction,
        stable_workflow=intent.stable_workflow,
        locked_asset=intent.locked_asset,
        active_campaign=intent.active_campaign,
        existing_rule_candidates=intent.existing_rule_candidates,
        conflict=intent.conflict,
        supersede=intent.supersede,
        auto_write=intent.auto_write,
        record_response_event=record_response_event,
    )


def receive_owner_correction(
    correction: str,
    *,
    business_id: str,
    biblia_root: Path,
    registry_path: Path | None = None,
    cronicas_sink: Any = None,
    learning: LearningIntent | None = None,
    correction_id: str = "owner-correction",
    correction_memory: Any = None,
):
    """Receive a direct owner correction and pass it through the canonical learning loop."""
    if not isinstance(correction,str) or not correction.strip():
        raise ValueError("OWNER_CORRECTION_REQUIRED")
    from .apokrisis import apokrisis
    response=apokrisis(
        angel_id="OMAR.OWNER-INPUT",
        mission_id=correction_id,
        status="SUCCESS",
        summary="Direct owner correction received",
        business_id=business_id,
        correction_signals=(correction.strip(),),
    )
    intent=learning or LearningIntent()
    if learning is None:
        from .durability import assess_durability
        repeated=False
        if correction_memory is not None:
            repeated=correction_memory.observe(business_id,correction) >= 2
        assessment=assess_durability(correction,repeated_correction=repeated)
        intent=LearningIntent(
            explicit_durable_instruction=assessment.reason=="EXPLICIT_DURABLE_LANGUAGE",
            repeated_correction=repeated,
        )
    return receive_apokrisis(
        response,
        biblia_root=biblia_root,
        registry_path=registry_path,
        cronicas_sink=cronicas_sink,
        learning=intent,
    )


@dataclass(frozen=True)
class OmarMissionDispatch:
    """OMAR's prepared mission result: isolated knowledge plus dispatch decision."""
    context: MissionContext
    decision: Any


def dispatch_mission(
    mission: dict[str, Any],
    *,
    biblia_root: Path,
    routes_path: Path | None = None,
    registry_path: Path | None = None,
    cronicas_sink: Any = None,
    security_context: Any = None,
) -> OmarMissionDispatch:
    """Load canonical BIBLIA before EXAPOSTELLO dispatches the mission."""
    if not isinstance(mission,dict):
        raise ValueError("MISSION_OBJECT_REQUIRED")
    business_id=mission.get("business_id")
    if not isinstance(business_id,str) or not business_id.strip():
        raise ValueError("MISSION_BUSINESS_ID_REQUIRED")

    context=prepare_mission(
        business_id,
        biblia_root=biblia_root,
        registry_path=registry_path,
    )

    from .router import exapostello
    decision=exapostello(
        mission,
        routes_path=routes_path,
        registry_path=registry_path,
        cronicas_sink=cronicas_sink,
        security_context=security_context,
    )
    return OmarMissionDispatch(context=context,decision=decision)


@dataclass(frozen=True)
class AngelExecutionContext:
    """Bounded ANGEL commission paired with OMAR's already-isolated knowledge."""
    commission: Any
    mission_context: MissionContext

    @property
    def knowledge(self) -> str:
        return self.mission_context.knowledge


def execution_contexts(dispatch: OmarMissionDispatch) -> tuple[AngelExecutionContext, ...]:
    """Materialize execution contexts only for commissions authorized by EXAPOSTELLO."""
    decision=dispatch.decision
    if getattr(decision,"action",None)!="DISPATCH":
        return ()
    contexts=[]
    for commission in getattr(decision,"angels",()) or ():
        if commission.business_id != dispatch.context.business_id:
            raise ValueError("ANGEL_CONTEXT_BUSINESS_MISMATCH")
        if tuple(commission.context_refs) != tuple(dispatch.context.biblia.refs):
            raise ValueError("ANGEL_CONTEXT_REFS_MISMATCH")
        contexts.append(
            AngelExecutionContext(
                commission=commission,
                mission_context=dispatch.context,
            )
        )
    return tuple(contexts)
