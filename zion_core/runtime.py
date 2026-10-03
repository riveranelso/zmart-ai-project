"""Runtime composition for OMAR using local persistence adapters.

This module wires existing ZION CORE ports together. It intentionally does not
select or configure production infrastructure.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .router import DispatchDecision
from .registry import sanpedro_resolve
from .holy_ghost import SCOPE_DESTINATION_NAMES
from .omar import (
    LearningIntent,
    dispatch_mission,
    receive_apokrisis,
    receive_owner_correction,
)
from .persistence import CronicasJsonlSink, LocalOperationLock, PersistentCorrectionMemory, read_cronicas


@dataclass(frozen=True)
class OmarCloseResult:
    processed: bool
    reason: str
    event: Any = None
    cycle: Any = None


@dataclass(frozen=True)
class OmarRuntime:
    biblia_root: Path
    cronicas_path: Path
    correction_memory_path: Path
    registry_path: Path | None = None
    routes_path: Path | None = None

    @property
    def cronicas_sink(self) -> CronicasJsonlSink:
        return CronicasJsonlSink(self.cronicas_path)

    @property
    def correction_memory(self) -> PersistentCorrectionMemory:
        return PersistentCorrectionMemory(self.correction_memory_path)

    @property
    def operation_lock(self) -> LocalOperationLock:
        return LocalOperationLock(self.cronicas_path.parent/(self.cronicas_path.name+".locks"))

    def dispatch(self, mission: dict[str, Any], *, security_context: Any = None):
        if not isinstance(mission,dict):
            raise ValueError("MISSION_OBJECT_REQUIRED")
        mission_id=mission.get("mission_id")
        business_id=mission.get("business_id")
        if isinstance(mission_id,str) and mission_id.strip() and isinstance(business_id,str) and business_id.strip():
            mid=mission_id.strip()
            bid=business_id.strip()
            with self.operation_lock.hold(bid,"MISSION_DISPATCH",mid):
                prior=self.history(business_id=bid,event_type="MISSION_DECISION",mission_id=mid)
                if prior:
                    from .omar import prepare_mission, OmarMissionDispatch
                    event=prior[-1]
                    # Reusing a mission id with different routing identity is
                    # not an idempotent retry; fail closed instead of silently
                    # returning the earlier decision.
                    requested_intent=mission.get("intent")
                    routes={}
                    if isinstance(requested_intent,str):
                        from .router import load_derekh
                        routes=load_derekh(self.routes_path)
                    expected_route=routes.get(requested_intent)
                    if expected_route is None:
                        # CRONICAS does not persist the original unknown intent,
                        # so exact unknown-route retries cannot currently be
                        # distinguished from conflicting unknown intents.
                        # Preserve the established retry contract here; routed
                        # decisions still fail closed if reused as unknown.
                        if event.command is not None or event.host is not None:
                            raise ValueError("MISSION_ID_REUSE_CONFLICT")
                    else:
                        expected_command,expected_host=expected_route
                        if event.command != expected_command or event.host != expected_host:
                            raise ValueError("MISSION_ID_REUSE_CONFLICT")
                    context=prepare_mission(bid,biblia_root=self.biblia_root,registry_path=self.registry_path)
                    decision=DispatchDecision(
                        mission_id=event.mission_id,action="IDEMPOTENT_NOOP",
                        reason="MISSION_ALREADY_DECIDED",business_id=event.business_id,
                    )
                    return OmarMissionDispatch(context=context,decision=decision)
                return dispatch_mission(
                    mission,biblia_root=self.biblia_root,routes_path=self.routes_path,
                    registry_path=self.registry_path,cronicas_sink=self.cronicas_sink,
                    security_context=security_context,
                )
        return dispatch_mission(
            mission,biblia_root=self.biblia_root,routes_path=self.routes_path,
            registry_path=self.registry_path,cronicas_sink=self.cronicas_sink,
            security_context=security_context,
        )

    def close(self, response: Any, *, learning: LearningIntent | None = None):
        business_id=getattr(response,"business_id",None)
        mission_id=getattr(response,"mission_id",None)
        angel_id=getattr(response,"angel_id",None)
        if all(isinstance(value,str) and value.strip() for value in (business_id,mission_id,angel_id)):
            bid=business_id.strip()
            mid=mission_id.strip()
            aid=angel_id.strip()
            identity=mid+"\x1f"+aid
            with self.operation_lock.hold(bid,"APOKRISIS",identity):
                prior=self.history(
                    business_id=bid,event_type="ANGEL_RESPONSE",mission_id=mid,
                )
                if any(aid in event.angel_ids for event in prior):
                    correction_signals=tuple(
                        value for value in (getattr(response,"correction_signals",()) or ())
                        if isinstance(value,str) and value.strip()
                    )
                    auto_write=True if learning is None else learning.auto_write
                    durable_learning=bool(
                        learning is not None and (
                            learning.scope_hint is not None
                            or learning.explicit_durable_instruction
                            or learning.repeated_correction
                            or learning.stable_workflow
                            or learning.locked_asset
                            or learning.active_campaign
                        )
                    )
                    attributed_mutation=any(
                        str(response.angel_id) in mutation.angel_ids
                        for mutation in self.history(
                            business_id=bid,event_type="BIBLIA_MUTATION",
                            mission_id=mid,
                        )
                    )
                    if (not correction_signals or not auto_write
                            or not durable_learning or attributed_mutation):
                        return OmarCloseResult(
                            processed=False,reason="APOKRISIS_ALREADY_PROCESSED",
                        )
                    event,cycle=receive_apokrisis(
                        response,biblia_root=self.biblia_root,
                        registry_path=self.registry_path,cronicas_sink=self.cronicas_sink,
                        learning=learning,record_response_event=False,
                    )
                    if getattr(cycle,"grapho",None) is None:
                        return OmarCloseResult(
                            processed=False,reason="APOKRISIS_ALREADY_PROCESSED",
                            cycle=cycle,
                        )
                    return OmarCloseResult(
                        processed=True,reason="APOKRISIS_LEARNING_RECOVERED",
                        event=event,cycle=cycle,
                    )
                event,cycle=receive_apokrisis(
                    response,biblia_root=self.biblia_root,
                    registry_path=self.registry_path,cronicas_sink=self.cronicas_sink,
                    learning=learning,
                )
                return OmarCloseResult(
                    processed=True,reason="APOKRISIS_PROCESSED",event=event,cycle=cycle,
                )
        event,cycle=receive_apokrisis(
            response,biblia_root=self.biblia_root,
            registry_path=self.registry_path,cronicas_sink=self.cronicas_sink,
            learning=learning,
        )
        return OmarCloseResult(
            processed=True,reason="APOKRISIS_PROCESSED",event=event,cycle=cycle,
        )


    def history(
        self,
        *,
        business_id: str | None = None,
        event_type: str | None = None,
        mission_id: str | None = None,
    ):
        """Read historical metadata only; never replay or execute recorded actions."""
        return read_cronicas(
            self.cronicas_path,
            business_id=business_id,
            event_type=event_type,
            mission_id=mission_id,
        )

    def mission_history(self, mission_id: str, *, business_id: str | None = None):
        """Reconstruct the recorded timeline for one mission without side effects."""
        if not isinstance(mission_id,str) or not mission_id.strip():
            raise ValueError("MISSION_ID_REQUIRED")
        return self.history(
            business_id=business_id,
            mission_id=mission_id.strip(),
        )

    def reconcile_biblia_mutation(self, decision: Any):
        """Repair missing mutation history without replaying work or rewriting BIBLIA."""
        business_id=getattr(decision,"business_id",None)
        mission_id=getattr(decision,"mission_id",None)
        destination_ref=getattr(decision,"destination_ref",None)
        if not all(isinstance(value,str) and value.strip()
                   for value in (business_id,mission_id,destination_ref)):
            raise ValueError("RECONCILIATION_IDENTITY_REQUIRED")
        bid=business_id.strip()
        mid=mission_id.strip()
        ref=destination_ref.strip()
        action=getattr(decision,"action",None)
        if action not in {"ADD","UPDATE","SUPERSEDE"}:
            raise ValueError("RECONCILIATION_ACTION_NOT_MUTATING")
        scope=getattr(decision,"scope",None)
        expected_name=SCOPE_DESTINATION_NAMES.get(scope) if isinstance(scope,str) else None
        if expected_name is None or Path(ref).name != expected_name:
            raise ValueError("RECONCILIATION_SCOPE_DESTINATION_MISMATCH")
        context=sanpedro_resolve(bid,self.registry_path)
        ref_path=Path(ref)
        authorized_names={Path(item).name for item in context.context_refs}
        if ref_path.name not in authorized_names or len(ref_path.parts)!=1:
            raise ValueError("RECONCILIATION_DESTINATION_NOT_AUTHORIZED")
        root=self.biblia_root.resolve()
        target=(self.biblia_root/ref_path.name).resolve()
        if root not in target.parents and target != root:
            raise ValueError("RECONCILIATION_DESTINATION_OUTSIDE_BIBLIA_ROOT")
        with self.operation_lock.hold(bid,"BIBLIA_RECONCILIATION",mid):
            prior=self.history(
                business_id=bid,event_type="BIBLIA_MUTATION",mission_id=mid,
            )
            if any(
                event.action==action
                and event.evidence_refs==(ref,)
                and event.status in {"CHANGED","RECONCILED"}
                for event in prior
            ):
                return None
            from .grapho import grapho_reconcile_committed_mutation
            return grapho_reconcile_committed_mutation(
                target,
                decision,
                self.cronicas_sink,
            )

    def owner_correction(
        self,
        correction: str,
        *,
        business_id: str,
        learning: LearningIntent | None = None,
        correction_id: str = "owner-correction",
    ):
        if not isinstance(correction_id,str) or not correction_id.strip():
            raise ValueError("CORRECTION_ID_REQUIRED")
        cid=correction_id.strip()
        with self.operation_lock.hold(business_id,"OWNER_CORRECTION",cid):
            prior=self.history(
                business_id=business_id,
                event_type="ANGEL_RESPONSE",
                mission_id=cid,
            )
            if any("OMAR.OWNER-INPUT" in event.angel_ids for event in prior):
                owner_mutation=any(
                    "OMAR.OWNER-INPUT" in mutation.angel_ids
                    for mutation in self.history(
                        business_id=business_id,event_type="BIBLIA_MUTATION",
                        mission_id=cid,
                    )
                )
                auto_write=True if learning is None else learning.auto_write
                recovery_learning=learning
                if recovery_learning is None:
                    from .durability import assess_durability
                    repeated=self.correction_memory.count(
                        business_id,correction
                    ) >= 2
                    assessment=assess_durability(
                        correction,
                        repeated_correction=repeated,
                    )
                    if not assessment.durable:
                        return OmarCloseResult(
                            processed=False,
                            reason="OWNER_CORRECTION_ALREADY_PROCESSED",
                        )
                    recovery_learning=LearningIntent(
                        explicit_durable_instruction=(
                            assessment.reason=="EXPLICIT_DURABLE_LANGUAGE"
                        ),
                        repeated_correction=repeated,
                    )
                durable_learning=bool(
                    recovery_learning.scope_hint is not None
                    or recovery_learning.explicit_durable_instruction
                    or recovery_learning.repeated_correction
                    or recovery_learning.stable_workflow
                    or recovery_learning.locked_asset
                    or recovery_learning.active_campaign
                )
                if not auto_write or not durable_learning or owner_mutation:
                    return OmarCloseResult(
                        processed=False,
                        reason="OWNER_CORRECTION_ALREADY_PROCESSED",
                    )
                event,cycle=receive_owner_correction(
                    correction,
                    business_id=business_id,
                    biblia_root=self.biblia_root,
                    registry_path=self.registry_path,
                    cronicas_sink=self.cronicas_sink,
                    learning=recovery_learning,
                    correction_id=cid,
                    correction_memory=self.correction_memory,
                    record_response_event=False,
                )
                if getattr(cycle,"grapho",None) is None:
                    return OmarCloseResult(
                        processed=False,
                        reason="OWNER_CORRECTION_ALREADY_PROCESSED",
                        cycle=cycle,
                    )
                return OmarCloseResult(
                    processed=True,
                    reason="OWNER_CORRECTION_LEARNING_RECOVERED",
                    event=event,
                    cycle=cycle,
                )
            event,cycle=receive_owner_correction(
                correction,
                business_id=business_id,
                biblia_root=self.biblia_root,
                registry_path=self.registry_path,
                cronicas_sink=self.cronicas_sink,
                learning=learning,
                correction_id=cid,
                correction_memory=self.correction_memory,
            )
            return OmarCloseResult(
                processed=True,
                reason="OWNER_CORRECTION_PROCESSED",
                event=event,
                cycle=cycle,
            )

