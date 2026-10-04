"""Batch mission planning for bounded, resumable ZION work.

This module plans independent mission items. Execution remains delegated to
OmarRuntime so existing tenant isolation, idempotency, routing and CRONICAS
authority are preserved.
"""
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable


@dataclass(frozen=True)
class BatchItem:
    item_key: str
    mission_id: str
    mission: dict[str, Any]


@dataclass(frozen=True)
class BatchPlan:
    batch_id: str
    business_id: str
    items: tuple[BatchItem, ...]


def _canonical(value: str, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(error)
    if value != value.strip():
        raise ValueError(error)
    return value


def _mission_id(batch_id: str, item_key: str) -> str:
    digest=hashlib.sha256((batch_id+"\x1f"+item_key).encode("utf-8")).hexdigest()[:20]
    return f"{batch_id}:{digest}"


def plan_batch(
    *,
    batch_id: str,
    business_id: str,
    intent: str,
    requested_by: str,
    scope: str,
    item_keys: Iterable[str],
    mission_defaults: dict[str, Any] | None = None,
) -> BatchPlan:
    """Build deterministic tenant-scoped missions for independent batch items."""
    batch_id=_canonical(batch_id,"BATCH_ID_REQUIRED")
    business_id=_canonical(business_id,"BATCH_BUSINESS_REQUIRED")
    intent=_canonical(intent,"BATCH_INTENT_REQUIRED")
    requested_by=_canonical(requested_by,"BATCH_REQUESTER_REQUIRED")
    scope=_canonical(scope,"BATCH_SCOPE_REQUIRED")
    if mission_defaults is not None and not isinstance(mission_defaults,dict):
        raise ValueError("BATCH_DEFAULTS_INVALID")
    defaults=dict(mission_defaults or {})
    protected={"mission_id","business_id","intent","requested_by","scope","payload_ref"}
    if protected.intersection(defaults):
        raise ValueError("BATCH_DEFAULTS_OVERRIDE_IDENTITY")

    seen=set()
    items=[]
    for raw_key in item_keys:
        key=_canonical(raw_key,"BATCH_ITEM_KEY_REQUIRED")
        if key in seen:
            raise ValueError("BATCH_ITEM_KEY_DUPLICATE")
        seen.add(key)
        mission_id=_mission_id(batch_id,key)
        mission={
            **defaults,
            "mission_id":mission_id,
            "business_id":business_id,
            "intent":intent,
            "requested_by":requested_by,
            "scope":scope,
            "payload_ref":key,
        }
        # Force deterministic JSON-serializable mission inputs now, not halfway
        # through a long batch.
        json.dumps(mission,sort_keys=True,separators=(",",":"))
        items.append(BatchItem(item_key=key,mission_id=mission_id,mission=mission))
    return BatchPlan(batch_id=batch_id,business_id=business_id,items=tuple(items))


def pending_items(plan: BatchPlan, runtime: Any) -> tuple[BatchItem, ...]:
    """Return only items without a durable mission decision.

    This is the checkpoint/resume boundary: completed/denied/reviewed items are
    not redispatched. OmarRuntime still owns retry validation if a caller
    explicitly dispatches an existing mission.
    """
    pending=[]
    for item in plan.items:
        history=runtime.history(
            business_id=plan.business_id,
            event_type="MISSION_DECISION",
            mission_id=item.mission_id,
        )
        if not history:
            pending.append(item)
    return tuple(pending)


@dataclass(frozen=True)
class PatternObservation:
    business_id: str
    pattern_key: str
    outcome: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternCandidate:
    business_id: str
    pattern_key: str
    outcome: str | None
    observation_count: int
    evidence_refs: tuple[str, ...]
    reusable: bool
    requires_review: bool
    reason: str


def assess_pattern_reuse(
    observations: Iterable[PatternObservation],
    *,
    minimum_observations: int = 2,
) -> PatternCandidate:
    """Aggregate repeated batch observations as review evidence, never authority."""
    values=tuple(observations)
    if not isinstance(minimum_observations,int) or isinstance(minimum_observations,bool) or minimum_observations < 2:
        raise ValueError("PATTERN_MINIMUM_INVALID")
    if not values:
        raise ValueError("PATTERN_OBSERVATIONS_REQUIRED")
    business_id=_canonical(values[0].business_id,"PATTERN_BUSINESS_REQUIRED")
    pattern_key=_canonical(values[0].pattern_key,"PATTERN_KEY_REQUIRED")
    outcomes=[]
    evidence=[]
    for item in values:
        if _canonical(item.business_id,"PATTERN_BUSINESS_REQUIRED") != business_id:
            raise ValueError("PATTERN_CROSS_TENANT_CONFLICT")
        if _canonical(item.pattern_key,"PATTERN_KEY_REQUIRED") != pattern_key:
            raise ValueError("PATTERN_KEY_CONFLICT")
        outcome=_canonical(item.outcome,"PATTERN_OUTCOME_REQUIRED")
        outcomes.append(outcome)
        for ref in item.evidence_refs:
            ref=_canonical(ref,"PATTERN_EVIDENCE_INVALID")
            if ref not in evidence:
                evidence.append(ref)
    unique_outcomes=tuple(dict.fromkeys(outcomes))
    if len(unique_outcomes) != 1:
        return PatternCandidate(
            business_id,pattern_key,None,len(values),tuple(evidence),
            False,True,"PATTERN_OUTCOME_CONFLICT",
        )
    if len(values) < minimum_observations:
        return PatternCandidate(
            business_id,pattern_key,unique_outcomes[0],len(values),tuple(evidence),
            False,True,"PATTERN_EVIDENCE_INSUFFICIENT",
        )
    return PatternCandidate(
        business_id,pattern_key,unique_outcomes[0],len(values),tuple(evidence),
        True,True,"PATTERN_REPEATED_EVIDENCE",
    )


@dataclass(frozen=True)
class BatchDispatchFailure:
    item_key: str
    mission_id: str
    error_type: str
    error_code: str


@dataclass(frozen=True)
class BatchDispatchResult:
    batch_id: str
    business_id: str
    attempted: tuple[str, ...]
    remaining: tuple[str, ...]
    decisions: tuple[Any, ...]
    failures: tuple[BatchDispatchFailure, ...] = ()


def dispatch_pending(
    plan: BatchPlan,
    runtime: Any,
    *,
    limit: int = 25,
    security_context: Any = None,
) -> BatchDispatchResult:
    """Dispatch a bounded slice of pending items through OmarRuntime.

    The runner owns no retry or tenant authority. It asks pending_items for the
    durable checkpoint, then delegates every selected mission to OmarRuntime.
    """
    if not isinstance(limit,int) or isinstance(limit,bool) or limit < 1:
        raise ValueError("BATCH_LIMIT_INVALID")
    pending=pending_items(plan,runtime)
    selected=pending[:limit]
    decisions=[]
    failures=[]
    for item in selected:
        try:
            result=runtime.dispatch(dict(item.mission),security_context=security_context)
            decisions.append(result.decision)
        except Exception as exc:
            # Keep the item pending. Store only exception class + stable code;
            # never persist arbitrary exception text that may contain payload/PII.
            code=getattr(exc,"code",None)
            if not isinstance(code,str) or not code.strip():
                code=exc.args[0] if len(exc.args)==1 and isinstance(exc.args[0],str) else type(exc).__name__
            failures.append(BatchDispatchFailure(
                item.item_key,item.mission_id,type(exc).__name__,str(code)[:128],
            ))
    remaining=pending_items(plan,runtime)
    return BatchDispatchResult(
        batch_id=plan.batch_id,
        business_id=plan.business_id,
        attempted=tuple(item.item_key for item in selected),
        remaining=tuple(item.item_key for item in remaining),
        decisions=tuple(decisions),
        failures=tuple(failures),
    )


@dataclass(frozen=True)
class BatchStatus:
    batch_id: str
    business_id: str
    total: int
    decided: int
    pending: int
    decision_actions: tuple[tuple[str, int], ...]


def batch_status(plan: BatchPlan, runtime: Any) -> BatchStatus:
    """Summarize durable batch progress without reading payload contents."""
    counts={}
    decided=0
    for item in plan.items:
        history=runtime.history(
            business_id=plan.business_id,
            event_type="MISSION_DECISION",
            mission_id=item.mission_id,
        )
        if not history:
            continue
        decided+=1
        action=getattr(history[-1],"action",None)
        action=action if isinstance(action,str) and action.strip() else "UNKNOWN"
        counts[action]=counts.get(action,0)+1
    total=len(plan.items)
    return BatchStatus(
        batch_id=plan.batch_id,
        business_id=plan.business_id,
        total=total,
        decided=decided,
        pending=total-decided,
        decision_actions=tuple(sorted(counts.items())),
    )
