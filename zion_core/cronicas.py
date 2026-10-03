"""CRONICAS structured event records and safe event emission."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

@dataclass(frozen=True)
class CronicaEvent:
    event_id:str
    occurred_at:str
    event_type:str
    mission_id:str
    action:str
    reason:str
    business_id:str|None=None
    command:str|None=None
    host:str|None=None
    denied_by:str|None=None
    angel_ids:tuple[str,...]=()
    correlation_id:str|None=None
    status:str|None=None
    evidence_refs:tuple[str,...]=()
    uncertainty_count:int=0
    correction_count:int=0
    def to_dict(self)->dict[str,Any]: return asdict(self)

CronicasSink = Callable[[CronicaEvent], None]

def build_routing_event(mission:dict[str,Any],decision:Any)->CronicaEvent:
    angels=getattr(decision,"angels",()) or ()
    correlation_id=mission.get("correlation_id")
    if correlation_id is not None and (
        not isinstance(correlation_id,str) or not correlation_id.strip()
    ):
        raise ValueError("INVALID_CORRELATION_ID")
    return CronicaEvent(
        event_id=str(uuid4()),
        occurred_at=datetime.now(timezone.utc).isoformat(),
        event_type="MISSION_DECISION",
        mission_id=str(decision.mission_id),
        action=str(decision.action),
        reason=str(decision.reason),
        business_id=getattr(decision,"business_id",None),
        command=getattr(decision,"command",None),
        host=getattr(decision,"host",None),
        denied_by=getattr(decision,"denied_by",None),
        angel_ids=tuple(a.angel_id for a in angels),
        correlation_id=correlation_id.strip() if correlation_id is not None else None,
    )

def cronicas_emit(mission:dict[str,Any],decision:Any,sink:CronicasSink|None=None)->CronicaEvent:
    """Build a privacy-bounded CRONICAS event and optionally deliver it to an injected sink."""
    event=build_routing_event(mission,decision)
    if sink is not None:
        sink(event)
    return event


class CronicasMemorySink:
    """Append-only in-memory sink for tests and non-persistent runtime use."""
    def __init__(self)->None:
        self._events:list[CronicaEvent]=[]

    def __call__(self,event:CronicaEvent)->None:
        if not isinstance(event,CronicaEvent):
            raise TypeError("CRONICAS_EVENT_REQUIRED")
        self._events.append(event)

    @property
    def events(self)->tuple[CronicaEvent,...]:
        return tuple(self._events)

def build_apokrisis_event(response:Any)->CronicaEvent:
    """Convert an APOKRISIS into privacy-bounded historical metadata."""
    return CronicaEvent(
        event_id=str(uuid4()),
        occurred_at=datetime.now(timezone.utc).isoformat(),
        event_type="ANGEL_RESPONSE",
        mission_id=str(response.mission_id),
        action="APOKRISIS",
        reason=str(response.error_code or response.status),
        business_id=str(response.business_id),
        angel_ids=(str(response.angel_id),),
        correlation_id=response.correlation_id,
        status=str(response.status),
        evidence_refs=tuple(response.evidence_refs),
        uncertainty_count=len(response.uncertainty),
        correction_count=len(response.correction_signals),
    )

def cronicas_emit_apokrisis(response:Any,sink:CronicasSink|None=None)->CronicaEvent:
    event=build_apokrisis_event(response)
    if sink is not None:
        sink(event)
    return event


def build_grapho_event(decision:Any,result:Any,origin_angel_id:str|None=None,correlation_id:str|None=None)->CronicaEvent:
    """Record BIBLIA mutation metadata without storing rule contents."""
    for name,value in (("ORIGIN_ANGEL_ID",origin_angel_id),("CORRELATION_ID",correlation_id)):
        if value is not None and (not isinstance(value,str) or not value.strip()):
            raise ValueError("INVALID_GRAPHO_"+name)
    return CronicaEvent(
        event_id=str(uuid4()),
        occurred_at=datetime.now(timezone.utc).isoformat(),
        event_type="BIBLIA_MUTATION",
        mission_id=str(decision.mission_id),
        action=str(result.action),
        reason=str(result.reason),
        business_id=str(decision.business_id),
        angel_ids=(origin_angel_id.strip(),) if origin_angel_id is not None else (),
        correlation_id=correlation_id.strip() if correlation_id is not None else None,
        status="RECONCILED" if result.reason=="RECONCILED_ALREADY_COMMITTED" else ("CHANGED" if result.changed else "UNCHANGED"),
        evidence_refs=(str(result.destination_ref),) if result.destination_ref else (),
        correction_count=len(getattr(decision,"proposed_rules",()) or ()),
    )

def cronicas_emit_grapho(decision:Any,result:Any,sink:CronicasSink|None=None,*,origin_angel_id:str|None=None,correlation_id:str|None=None)->CronicaEvent:
    event=build_grapho_event(decision,result,origin_angel_id,correlation_id)
    if sink is not None:
        sink(event)
    return event
