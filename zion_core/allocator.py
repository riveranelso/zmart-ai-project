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
    if not isinstance(count,int) or isinstance(count,bool) or count<1:
        raise ValueError("INVALID_ANGEL_COUNT")
    return tuple(
        DiatassoCommission(
            angel_id=f"{host}.ANGEL-{i:03d}",
            mission_id=str(mission["mission_id"]),
            command=command,
            host=host,
            business_id=business_id,
            isolation_key=isolation_key,
            scope=str(mission["scope"]),
            context_refs=context_refs,
            payload_ref=mission.get("payload_ref"),
        )
        for i in range(1,count+1)
    )


AngelAssignment = DiatassoCommission  # compatibility alias

def allocate_angels(*, mission:dict[str,Any], command:str, host:str, business_id:str,
                    isolation_key:str, context_refs:tuple[str,...])->tuple[DiatassoCommission,...]:
    """Compatibility alias. New ZION code should use DIATASSO."""
    return diatasso(mission=mission,command=command,host=host,business_id=business_id,
                    isolation_key=isolation_key,context_refs=context_refs)
