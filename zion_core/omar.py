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
    mission_id: str | None = None
    scope: str | None = None
    payload_ref: str | None = None

    @property
    def knowledge(self) -> str:
        return self.biblia.text


def prepare_mission(
    business_id: str,
    *,
    biblia_root: Path,
    registry_path: Path | None = None,
    mission_id: str | None = None,
    scope: str | None = None,
    payload_ref: str | None = None,
) -> MissionContext:
    """Load isolated canonical knowledge before OMAR dispatches a mission."""
    biblia=retrieve_biblia(
        business_id,
        root=biblia_root,
        registry_path=registry_path,
    )
    return MissionContext(business_id=business_id,biblia=biblia,mission_id=mission_id,scope=scope,payload_ref=payload_ref)


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
    record_response_event: bool = True,
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
        record_response_event=record_response_event,
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
        mission_id=mission.get("mission_id"),
        scope=mission.get("scope"),
        payload_ref=mission.get("payload_ref"),
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
    if getattr(decision,"business_id",None) != dispatch.context.business_id:
        raise ValueError("ANGEL_CONTEXT_DECISION_BUSINESS_MISMATCH")
    if getattr(decision,"mission_id",None) != dispatch.context.mission_id:
        raise ValueError("ANGEL_CONTEXT_DECISION_MISSION_MISMATCH")
    if getattr(decision,"scope",None) != dispatch.context.scope:
        raise ValueError("ANGEL_CONTEXT_DECISION_SCOPE_MISMATCH")
    if getattr(decision,"payload_ref",None) != dispatch.context.payload_ref:
        raise ValueError("ANGEL_CONTEXT_DECISION_PAYLOAD_MISMATCH")
    if dispatch.context.biblia.business_id != dispatch.context.business_id:
        raise ValueError("ANGEL_CONTEXT_BIBLIA_BUSINESS_MISMATCH")
    if tuple(getattr(decision,"context_refs",()) or ()) != tuple(dispatch.context.biblia.refs):
        raise ValueError("ANGEL_CONTEXT_DECISION_REFS_MISMATCH")
    expected_isolation_key=dispatch.context.business_id
    if getattr(decision,"isolation_key",None) != expected_isolation_key:
        raise ValueError("ANGEL_CONTEXT_DECISION_ISOLATION_MISMATCH")
    angels=getattr(decision,"angels",()) or ()
    angel_ids=[getattr(commission,"angel_id",None) for commission in angels]
    if any(not isinstance(angel_id,str) or not angel_id.strip() for angel_id in angel_ids):
        raise ValueError("ANGEL_CONTEXT_ID_INVALID")
    if len(set(angel_ids)) != len(angel_ids):
        raise ValueError("ANGEL_CONTEXT_DUPLICATE_ANGEL")
    angel_count=getattr(decision,"angel_count",None)
    if not isinstance(angel_count,int) or isinstance(angel_count,bool) or len(angels) != angel_count:
        raise ValueError("ANGEL_CONTEXT_COUNT_MISMATCH")
    host=getattr(decision,"host",None)
    expected_ids=[f"{host}.ANGEL-{index:03d}" for index in range(1,len(angels)+1)]
    if angel_ids != expected_ids:
        raise ValueError("ANGEL_CONTEXT_ID_MISMATCH")
    scopes={getattr(commission,"scope",None) for commission in angels}
    payload_refs={getattr(commission,"payload_ref",None) for commission in angels}
    if len(scopes) != 1:
        raise ValueError("ANGEL_CONTEXT_SCOPE_MISMATCH")
    if len(payload_refs) != 1:
        raise ValueError("ANGEL_CONTEXT_PAYLOAD_MISMATCH")
    for commission in angels:
        if commission.business_id != dispatch.context.business_id:
            raise ValueError("ANGEL_CONTEXT_BUSINESS_MISMATCH")
        if commission.isolation_key != getattr(decision,"isolation_key",None):
            raise ValueError("ANGEL_CONTEXT_ISOLATION_MISMATCH")
        if commission.mission_id != getattr(decision,"mission_id",None):
            raise ValueError("ANGEL_CONTEXT_MISSION_MISMATCH")
        if commission.scope != getattr(decision,"scope",None):
            raise ValueError("ANGEL_CONTEXT_SCOPE_MISMATCH")
        if commission.payload_ref != getattr(decision,"payload_ref",None):
            raise ValueError("ANGEL_CONTEXT_PAYLOAD_MISMATCH")
        if commission.command != getattr(decision,"command",None) or commission.host != getattr(decision,"host",None):
            raise ValueError("ANGEL_CONTEXT_ROUTE_MISMATCH")
        if tuple(commission.context_refs) != tuple(dispatch.context.biblia.refs):
            raise ValueError("ANGEL_CONTEXT_REFS_MISMATCH")
        contexts.append(
            AngelExecutionContext(
                commission=commission,
                mission_context=dispatch.context,
            )
        )
    return tuple(contexts)
