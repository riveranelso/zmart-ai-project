"""Runtime composition for OMAR using local persistence adapters.

This module wires existing ZION CORE ports together. It intentionally does not
select or configure production infrastructure.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .router import DispatchDecision
from .cronicas import build_apokrisis_fingerprint, build_dispatch_fingerprint
from .registry import canonical_business_id, sanpedro_resolve
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
        return CronicasJsonlSink(self.cronicas_path,registry_path=self.registry_path)

    @property
    def correction_memory(self) -> PersistentCorrectionMemory:
        return PersistentCorrectionMemory(
            self.correction_memory_path,registry_path=self.registry_path,
        )

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
            # Canonicalize once at ingress: alias spellings share one lock
            # namespace, one history partition, and one dispatch fingerprint.
            # Unknown business ids fail closed here (same SanPedroError the
            # old path raised later inside dispatch_mission).
            bid=canonical_business_id(business_id.strip(),self.registry_path)
            mission={**mission,"business_id":bid}
            with self.operation_lock.hold(bid,"MISSION_DISPATCH",mid):
                prior=self.history(business_id=bid,event_type="MISSION_DECISION",mission_id=mid)
                if prior:
                    from .omar import prepare_mission, OmarMissionDispatch
                    actions={event.action for event in prior}
                    if len(actions)>1:
                        raise ValueError("MISSION_CONFLICTING_HISTORY")
                    route_identities={(event.command,event.host) for event in prior}
                    if len(route_identities)>1:
                        raise ValueError("MISSION_CONFLICTING_HISTORY")
                    fingerprints={event.dispatch_fingerprint for event in prior}
                    if len(fingerprints)>1:
                        raise ValueError("MISSION_CONFLICTING_HISTORY")
                    commission_sets={tuple(event.angel_ids) for event in prior}
                    if len(commission_sets)>1:
                        raise ValueError("MISSION_CONFLICTING_HISTORY")
                    for prior_event in prior:
                        if prior_event.action=="DISPATCH":
                            if not prior_event.angel_ids or len(prior_event.angel_ids)!=len(set(prior_event.angel_ids)):
                                raise ValueError("MISSION_INVALID_COMMISSION_HISTORY")
                            if not isinstance(prior_event.host,str) or not prior_event.host.strip():
                                raise ValueError("MISSION_INVALID_COMMISSION_HISTORY")
                            expected=tuple(
                                f"{prior_event.host}.ANGEL-{index:03d}"
                                for index in range(1,len(prior_event.angel_ids)+1)
                            )
                            if tuple(prior_event.angel_ids)!=expected:
                                raise ValueError("MISSION_INVALID_COMMISSION_HISTORY")
                    event=prior[-1]
                    if event.action=="DISPATCH" and event.dispatch_fingerprint is None:
                        raise ValueError("MISSION_DISPATCH_FINGERPRINT_MISSING")
                    # Reusing a mission id with different routing identity is
                    # not an idempotent retry; fail closed instead of silently
                    # returning the earlier decision.
                    current_fingerprint=build_dispatch_fingerprint(mission,security_context)
                    if event.dispatch_fingerprint is not None:
                        if event.dispatch_fingerprint != current_fingerprint:
                            raise ValueError("MISSION_ID_REUSE_CONFLICT")
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
        if not all(isinstance(value,str) and value.strip() for value in (business_id,mission_id,angel_id)):
            raise ValueError("APOKRISIS_IDENTITY_REQUIRED")
        if all(isinstance(value,str) and value.strip() for value in (business_id,mission_id,angel_id)):
            # History partition and lock key use the canonical identity; the
            # response object itself keeps the angel's claimed id (the sink
            # normalizes the recorded event on write).
            bid=canonical_business_id(business_id.strip(),self.registry_path)
            mid=mission_id.strip()
            aid=angel_id.strip()
            if business_id != bid or mission_id != mid or angel_id != aid:
                raise ValueError("APOKRISIS_IDENTITY_NONCANONICAL")
            identity=mid+"\x1f"+aid
            with self.operation_lock.hold(bid,"APOKRISIS",identity):
                dispatch_events=self.history(
                    business_id=bid,event_type="MISSION_DECISION",mission_id=mid,
                )
                dispatched_events=[event for event in dispatch_events if event.action=="DISPATCH"]
                if dispatched_events and any(event.action!="DISPATCH" for event in dispatch_events):
                    raise ValueError("APOKRISIS_CONFLICTING_MISSION_HISTORY")
                if dispatch_events and not dispatched_events:
                    raise ValueError("APOKRISIS_MISSION_NOT_DISPATCHED")
                route_identities={(event.command,event.host) for event in dispatched_events}
                if len(route_identities)>1:
                    raise ValueError("APOKRISIS_CONFLICTING_ROUTE_HISTORY")
                dispatch_fingerprints={event.dispatch_fingerprint for event in dispatched_events}
                if len(dispatch_fingerprints)>1:
                    raise ValueError("APOKRISIS_CONFLICTING_DISPATCH_FINGERPRINTS")
                route_sets={(event.command,event.host) for event in dispatched_events}
                if len(route_sets)>1:
                    raise ValueError("APOKRISIS_CONFLICTING_ROUTE_HISTORY")
                commission_sets={tuple(event.angel_ids) for event in dispatched_events}
                if len(commission_sets)>1:
                    raise ValueError("APOKRISIS_CONFLICTING_COMMISSION_HISTORY")
                commissioned={
                    item for event in dispatched_events
                    for item in event.angel_ids
                }
                if dispatched_events and not commissioned:
                    raise ValueError("APOKRISIS_COMMISSION_EVIDENCE_MISSING")
                if any(len(event.angel_ids)!=len(set(event.angel_ids)) for event in dispatched_events):
                    raise ValueError("APOKRISIS_INVALID_COMMISSION_HISTORY")
                for event in dispatched_events:
                    if not isinstance(event.host,str) or not event.host.strip():
                        raise ValueError("APOKRISIS_INVALID_COMMISSION_HISTORY")
                    expected=tuple(
                        f"{event.host}.ANGEL-{index:03d}"
                        for index in range(1,len(event.angel_ids)+1)
                    )
                    if tuple(event.angel_ids)!=expected:
                        raise ValueError("APOKRISIS_INVALID_COMMISSION_HISTORY")
                if commissioned and aid not in commissioned:
                    raise ValueError("APOKRISIS_ANGEL_NOT_COMMISSIONED")
                prior=self.history(
                    business_id=bid,event_type="ANGEL_RESPONSE",mission_id=mid,
                )
                matching=[event for event in prior if aid in event.angel_ids]
                if any(tuple(event.angel_ids)!=(aid,) for event in matching):
                    raise ValueError("APOKRISIS_RESPONSE_IDENTITY_INVALID")
                if matching:
                    response_fingerprints={event.response_fingerprint for event in matching}
                    if len(response_fingerprints)>1:
                        raise ValueError("APOKRISIS_CONFLICTING_RESPONSE_HISTORY")
                    response_shapes={(
                        event.status,event.reason,event.correlation_id,event.evidence_refs,
                        event.uncertainty_count,event.correction_count,
                    ) for event in matching}
                    if len(response_shapes)>1:
                        raise ValueError("APOKRISIS_CONFLICTING_RESPONSE_HISTORY")
                    recorded=matching[-1]
                    if (recorded.response_fingerprint is not None
                            and recorded.response_fingerprint != build_apokrisis_fingerprint(response)):
                        raise ValueError("APOKRISIS_REUSE_CONFLICT")
                    current_evidence=tuple(getattr(response,"evidence_refs",()) or ())
                    current_uncertainty=len(getattr(response,"uncertainty",()) or ())
                    current_corrections=len(getattr(response,"correction_signals",()) or ())
                    current_correlation=getattr(response,"correlation_id",None)
                    current_status=getattr(response,"status",None)
                    current_reason=getattr(response,"error_code",None) or current_status
                    if (
                        recorded.status != current_status
                        or recorded.reason != current_reason
                        or recorded.correlation_id != current_correlation
                        or recorded.evidence_refs != current_evidence
                        or recorded.uncertainty_count != current_uncertainty
                        or recorded.correction_count != current_corrections
                    ):
                        raise ValueError("APOKRISIS_REUSE_CONFLICT")
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
        """Read historical metadata only; never replay or execute recorded actions.

        The business_id filter is normalized to the canonical tenant identity,
        so alias spellings read the same partition.
        """
        return read_cronicas(
            self.cronicas_path,
            business_id=canonical_business_id(business_id,self.registry_path),
            event_type=event_type,
            mission_id=mission_id,
            registry_path=self.registry_path,
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
        if business_id != business_id.strip() or mission_id != mission_id.strip() or destination_ref != destination_ref.strip():
            raise ValueError("RECONCILIATION_IDENTITY_NONCANONICAL")
        # Lock and history use the canonical identity; the decision object
        # keeps its original identity for traceability.
        bid=canonical_business_id(business_id,self.registry_path)
        mid=mission_id
        ref=destination_ref
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
        if correction_id != correction_id.strip():
            raise ValueError("CORRECTION_ID_NONCANONICAL")
        if not isinstance(business_id,str) or not business_id.strip() or business_id != business_id.strip():
            raise ValueError("BUSINESS_ID_REQUIRED")
        # Canonicalize once: lock, history, correction memory, and the
        # owner-correction apokrisis all share the canonical partition.
        business_id=canonical_business_id(business_id,self.registry_path)
        cid=correction_id
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

