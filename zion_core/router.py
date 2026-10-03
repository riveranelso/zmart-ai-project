"""SAN GABRIEL mission router with SAN PEDRO, gates and ANGEL allocation."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import json
from typing import Any
from .allocator import AngelAssignment, allocate_angels
from .gates import evaluate_gates
from .registry import RegistryError, resolve_business

ROOT=Path(__file__).resolve().parents[1]; CONFIG_DIR=ROOT/"zmart360"
ALLOWED_RISK={"low","medium","high","critical"}
class MissionValidationError(ValueError): pass

@dataclass(frozen=True)
class DispatchDecision:
    mission_id:str; action:str; reason:str
    command:str|None=None; host:str|None=None; angel_prefix:str|None=None
    angels:tuple[AngelAssignment,...]=()
    business_id:str|None=None; isolation_key:str|None=None; context_refs:tuple[str,...]=()
    denied_by:str|None=None; human_review_required:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

def load_derekh(path:Path|None=None)->dict[str,tuple[str,str]]:
    path=path or CONFIG_DIR/"derekh.yaml"; routes={}; intent=command=host=None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if line.startswith("- intent:"):
            if intent and command and host:
                if intent in routes: raise RuntimeError("DUPLICATE_ROUTE")
                routes[intent]=(command,host)
            intent=line.split(":",1)[1].strip(); command=host=None
        elif intent and line.startswith("command:"): command=line.split(":",1)[1].strip()
        elif intent and line.startswith("host:"): host=line.split(":",1)[1].strip()
        elif line=="fallback:": break
    if intent and command and host:
        if intent in routes: raise RuntimeError("DUPLICATE_ROUTE")
        routes[intent]=(command,host)
    for cmd,hst in routes.values():
        if not hst.startswith(cmd+".HOST-"): raise RuntimeError("INVALID_COMMAND_HOST_PAIR")
    return routes

def load_routes(path:Path|None=None)->dict[str,tuple[str,str]]:
    """Compatibility alias for DEREKH path loading."""
    return load_derekh(path)

def validate_mission(mission:dict[str,Any])->None:
    if not isinstance(mission,dict): raise MissionValidationError("MISSION_OBJECT_REQUIRED")
    required=("mission_id","intent","requested_by","scope","business_id")
    missing=[k for k in required if not mission.get(k)]
    if missing: raise MissionValidationError("MISSING_REQUIRED_FIELDS:"+",".join(missing))
    if mission.get("risk_level","low") not in ALLOWED_RISK: raise MissionValidationError("INVALID_RISK_LEVEL")
    count=mission.get("angel_count_max",1)
    if not isinstance(count,int) or isinstance(count,bool) or count<1: raise MissionValidationError("INVALID_ANGEL_COUNT")

def exapostello(mission:dict[str,Any],routes_path:Path|None=None,registry_path:Path|None=None)->DispatchDecision:
    validate_mission(mission); mid=str(mission["mission_id"]); bid=str(mission["business_id"])
    try: ctx=resolve_business(bid,registry_path)
    except RegistryError as exc:
        return DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW",str(exc),business_id=bid,human_review_required=True)
    base=dict(business_id=ctx.business_id,isolation_key=ctx.isolation_key,context_refs=ctx.context_refs)
    route=load_derekh(routes_path).get(str(mission["intent"]))
    if route is None: return DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW","ROUTE_NOT_FOUND",human_review_required=True,**base)
    command,host=route
    if mission.get("target_command") not in (None,command): return DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW","TARGET_COMMAND_CONFLICT",human_review_required=True,**base)
    if mission.get("target_host") not in (None,host): return DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW","TARGET_HOST_CONFLICT",human_review_required=True,**base)
    for gate in evaluate_gates(mission,ctx.isolation_key,ctx.context_refs):
        if not gate.allowed:
            return DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW",gate.reason,command=command,host=host,denied_by=gate.gate,human_review_required=True,**base)
    angels=allocate_angels(mission=mission,command=command,host=host,business_id=ctx.business_id,
                           isolation_key=ctx.isolation_key,context_refs=ctx.context_refs)
    return DispatchDecision(mid,"DISPATCH","ANGELS_ALLOCATED",command=command,host=host,
                            angel_prefix=host+".ANGEL-",angels=angels,**base)

def route_mission(mission:dict[str,Any],routes_path:Path|None=None,registry_path:Path|None=None)->DispatchDecision:
    """Compatibility alias for EXAPOSTELLO. New ZION code should call exapostello()."""
    return exapostello(mission,routes_path,registry_path)

def main()->None:
    import sys
    print(json.dumps(exapostello(json.load(sys.stdin)).to_dict(),indent=2))
if __name__=="__main__": main()
