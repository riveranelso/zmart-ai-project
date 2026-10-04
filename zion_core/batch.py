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
