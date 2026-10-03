"""CRONICAS structured event records. No persistence or external I/O."""
from dataclasses import asdict, dataclass
from typing import Any

@dataclass(frozen=True)
class CronicaEvent:
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
    def to_dict(self)->dict[str,Any]: return asdict(self)

def build_routing_event(mission:dict[str,Any],decision:Any)->CronicaEvent:
    angels=getattr(decision,"angels",()) or ()
    return CronicaEvent(
        event_type="MISSION_DECISION",
        mission_id=str(decision.mission_id),
        action=str(decision.action),
        reason=str(decision.reason),
        business_id=getattr(decision,"business_id",None),
        command=getattr(decision,"command",None),
        host=getattr(decision,"host",None),
        denied_by=getattr(decision,"denied_by",None),
        angel_ids=tuple(a.angel_id for a in angels),
        correlation_id=mission.get("correlation_id"),
    )
