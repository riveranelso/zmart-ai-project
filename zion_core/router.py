"""SAN GABRIEL mission router with SAN PEDRO, gates and ANGEL allocation."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import json
from typing import Any
from .cronicas import CronicasSink, cronicas_emit
from .allocator import DiatassoCommission, diatasso
from .gates import SecurityContext, evaluate_gates
from .registry import SanPedroError, sanpedro_resolve

ROOT=Path(__file__).resolve().parents[1]; CONFIG_DIR=ROOT/"zmart360"
ALLOWED_RISK={"low","medium","high","critical"}
MEGILLAH_FIELDS={"mission_id","intent","requested_by","scope","business_id","project_id","risk_level","human_approval_required","target_command","target_host","angel_count_max","payload_ref","correlation_id"}
class MissionValidationError(ValueError): pass

@dataclass(frozen=True)
class DispatchDecision:
    mission_id:str; action:str; reason:str
    command:str|None=None; host:str|None=None; angel_prefix:str|None=None
    angels:tuple[DiatassoCommission,...]=()
    business_id:str|None=None; isolation_key:str|None=None; context_refs:tuple[str,...]=()
    denied_by:str|None=None; human_review_required:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

def load_derekh(path:Path|None=None)->dict[str,tuple[str,str]]:
    path=path or CONFIG_DIR/"derekh.yaml"; routes={}; intent=command=host=None; in_routes=False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if line=="routes:":
            in_routes=True
            continue
        if not in_routes:
            continue
        if line=="fallback:":
            break
        if line.startswith("- intent:"):
            if intent and command and host:
                if intent in routes: raise RuntimeError("DUPLICATE_ROUTE")
                routes[intent]=(command,host)
            intent=line.split(":",1)[1].strip(); command=host=None
        elif intent and line.startswith("command:"): command=line.split(":",1)[1].strip()
        elif intent and line.startswith("host:"): host=line.split(":",1)[1].strip()
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
    """Validate the stable MEGILLAH core while allowing runtime extension signals."""
    if not isinstance(mission,dict):
        raise MissionValidationError("MISSION_OBJECT_REQUIRED")
    required=("mission_id","intent","requested_by","scope","business_id")
    missing=[k for k in required if not isinstance(mission.get(k),str) or not mission[k].strip()]
    if missing:
        raise MissionValidationError("MISSING_OR_INVALID_REQUIRED_FIELDS:"+",".join(missing))
    noncanonical=[k for k in required if mission[k] != mission[k].strip()]
    if noncanonical:
        raise MissionValidationError("NONCANONICAL_REQUIRED_FIELDS:"+",".join(noncanonical))
    if mission.get("risk_level","low") not in ALLOWED_RISK:
        raise MissionValidationError("INVALID_RISK_LEVEL")
    count=mission.get("angel_count_max",1)
    if not isinstance(count,int) or isinstance(count,bool) or count<1 or count>100:
        raise MissionValidationError("INVALID_ANGEL_COUNT")
    for key in ("human_approval_required","integrity_conflict","policy_conflict","kill_switch","runtime_enabled"):
        if key in mission and not isinstance(mission[key],bool):
            raise MissionValidationError("INVALID_BOOLEAN:"+key)
    for key in ("project_id","target_command","target_host","payload_ref","correlation_id","isolation_key"):
        if key in mission and mission[key] is not None:
            value=mission[key]
            if not isinstance(value,str):
                raise MissionValidationError("INVALID_STRING:"+key)
            if not value.strip():
                raise MissionValidationError("INVALID_STRING:"+key)
            if key != "correlation_id" and value != value.strip():
                raise MissionValidationError("INVALID_STRING:"+key)

def exapostello(mission:dict[str,Any],routes_path:Path|None=None,registry_path:Path|None=None,cronicas_sink:CronicasSink|None=None,security_context:SecurityContext|None=None)->DispatchDecision:
    validate_mission(mission); mid=str(mission["mission_id"]); bid=str(mission["business_id"])
    try: ctx=sanpedro_resolve(bid,registry_path)
    except SanPedroError as exc:
        decision=DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW",str(exc),business_id=bid,human_review_required=True)
        cronicas_emit(mission,decision,cronicas_sink,security_context=security_context); return decision
    base=dict(business_id=ctx.business_id,isolation_key=ctx.isolation_key,context_refs=ctx.context_refs)
    route=load_derekh(routes_path).get(str(mission["intent"]))
    if route is None:
        decision=DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW","ROUTE_NOT_FOUND",human_review_required=True,**base)
        cronicas_emit(mission,decision,cronicas_sink,security_context=security_context); return decision
    command,host=route
    if mission.get("target_command") not in (None,command):
        decision=DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW","TARGET_COMMAND_CONFLICT",human_review_required=True,**base)
        cronicas_emit(mission,decision,cronicas_sink,security_context=security_context); return decision
    if mission.get("target_host") not in (None,host):
        decision=DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW","TARGET_HOST_CONFLICT",human_review_required=True,**base)
        cronicas_emit(mission,decision,cronicas_sink,security_context=security_context); return decision
    for gate in evaluate_gates(mission,ctx.isolation_key,ctx.context_refs,security_context):
        if not gate.allowed:
            decision=DispatchDecision(mid,"REQUIRE_HUMAN_REVIEW",gate.reason,command=command,host=host,denied_by=gate.gate,human_review_required=True,**base)
            cronicas_emit(mission,decision,cronicas_sink,security_context=security_context); return decision
    angels=diatasso(mission=mission,command=command,host=host,business_id=ctx.business_id,
                           isolation_key=ctx.isolation_key,context_refs=ctx.context_refs)
    decision=DispatchDecision(mid,"DISPATCH","ANGELS_ALLOCATED",command=command,host=host,
                            angel_prefix=host+".ANGEL-",angels=angels,**base)
    cronicas_emit(mission,decision,cronicas_sink,security_context=security_context); return decision

def route_mission(mission:dict[str,Any],routes_path:Path|None=None,registry_path:Path|None=None)->DispatchDecision:
    """Compatibility alias for EXAPOSTELLO. New ZION code should call exapostello()."""
    return exapostello(mission,routes_path,registry_path)

def main()->None:
    import sys
    print(json.dumps(exapostello(json.load(sys.stdin)).to_dict(),indent=2))
if __name__=="__main__": main()
