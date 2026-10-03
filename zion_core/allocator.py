"""DIATASSO: deterministic bounded appointment of ANGELS to a mission."""
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class DiatassoCommission:
    angel_id: str
    mission_id: str
    command: str
    host: str
    business_id: str
    isolation_key: str
    scope: str
    context_refs: tuple[str, ...]
    payload_ref: str | None = None
    def to_dict(self)->dict[str,Any]: return asdict(self)

def diatasso(*, mission:dict[str,Any], command:str, host:str, business_id:str,
                    isolation_key:str, context_refs:tuple[str,...])->tuple[DiatassoCommission,...]:
    count=mission.get("angel_count_max",1)
    if not isinstance(count,int) or isinstance(count,bool) or count<1 or count>100:
        raise ValueError("INVALID_ANGEL_COUNT")
    mission_id=mission.get("mission_id")
    scope=mission.get("scope")
    if not isinstance(mission_id,str) or not mission_id.strip():
        raise ValueError("MISSION_ID_REQUIRED")
    if not isinstance(scope,str) or not scope.strip():
        raise ValueError("MISSION_SCOPE_REQUIRED")
    if not isinstance(command,str) or not command.strip() or not isinstance(host,str) or not host.strip():
        raise ValueError("COMMAND_HOST_REQUIRED")
    if not isinstance(business_id,str) or not business_id.strip():
        raise ValueError("BUSINESS_ID_REQUIRED")
    if not isinstance(isolation_key,str) or not isolation_key.strip():
        raise ValueError("ISOLATION_KEY_REQUIRED")
    if not isinstance(context_refs,tuple) or not context_refs or not all(
        isinstance(ref,str) and ref.strip() and ref==ref.strip()
        for ref in context_refs
    ):
        raise ValueError("CONTEXT_REFS_REQUIRED")
    payload_ref=mission.get("payload_ref")
    if payload_ref is not None and (
        not isinstance(payload_ref,str) or not payload_ref.strip()
    ):
        raise ValueError("INVALID_PAYLOAD_REF")
    return tuple(
        DiatassoCommission(
            angel_id=f"{host}.ANGEL-{i:03d}",
            mission_id=mission_id.strip(),
            command=command,
            host=host,
            business_id=business_id,
            isolation_key=isolation_key,
            scope=scope.strip(),
            context_refs=context_refs,
            payload_ref=payload_ref.strip() if payload_ref is not None else None,
        )
        for i in range(1,count+1)
    )


AngelAssignment = DiatassoCommission  # compatibility alias

def allocate_angels(*, mission:dict[str,Any], command:str, host:str, business_id:str,
                    isolation_key:str, context_refs:tuple[str,...])->tuple[DiatassoCommission,...]:
    """Compatibility alias. New ZION code should use DIATASSO."""
    return diatasso(mission=mission,command=command,host=host,business_id=business_id,
                    isolation_key=isolation_key,context_refs=context_refs)
