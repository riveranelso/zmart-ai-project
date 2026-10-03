"""Runtime composition for OMAR using local persistence adapters.

This module wires existing ZION CORE ports together. It intentionally does not
select or configure production infrastructure.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .router import DispatchDecision
from .omar import (
    LearningIntent,
    dispatch_mission,
    receive_apokrisis,
    receive_owner_correction,
)
from .persistence import CronicasJsonlSink, PersistentCorrectionMemory, read_cronicas


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

    def dispatch(self, mission: dict[str, Any], *, security_context: Any = None):
        if not isinstance(mission,dict):
            raise ValueError("MISSION_OBJECT_REQUIRED")
        mission_id=mission.get("mission_id")
        business_id=mission.get("business_id")
        if isinstance(mission_id,str) and mission_id.strip() and isinstance(business_id,str) and business_id.strip():
            prior=self.history(
                business_id=business_id.strip(),
                event_type="MISSION_DECISION",
                mission_id=mission_id.strip(),
            )
            if prior:
                from .omar import prepare_mission, OmarMissionDispatch
                context=prepare_mission(
                    business_id.strip(),
                    biblia_root=self.biblia_root,
                    registry_path=self.registry_path,
                )
                event=prior[-1]
                decision=DispatchDecision(
                    mission_id=event.mission_id,
                    action="IDEMPOTENT_NOOP",
                    reason="MISSION_ALREADY_DECIDED",
                    business_id=event.business_id,
                )
                return OmarMissionDispatch(context=context,decision=decision)
        return dispatch_mission(
            mission,
            biblia_root=self.biblia_root,
            routes_path=self.routes_path,
            registry_path=self.registry_path,
            cronicas_sink=self.cronicas_sink,
            security_context=security_context,
        )

    def close(self, response: Any, *, learning: LearningIntent | None = None):
        business_id=getattr(response,"business_id",None)
        mission_id=getattr(response,"mission_id",None)
        angel_id=getattr(response,"angel_id",None)
        if all(isinstance(value,str) and value.strip() for value in (business_id,mission_id,angel_id)):
            prior=self.history(
                business_id=business_id.strip(),
                event_type="ANGEL_RESPONSE",
                mission_id=mission_id.strip(),
            )
            if any(angel_id.strip() in event.angel_ids for event in prior):
                return OmarCloseResult(
                    processed=False,
                    reason="APOKRISIS_ALREADY_PROCESSED",
                )
        event,cycle=receive_apokrisis(
            response,
            biblia_root=self.biblia_root,
            registry_path=self.registry_path,
            cronicas_sink=self.cronicas_sink,
            learning=learning,
        )
        return OmarCloseResult(
            processed=True,
            reason="APOKRISIS_PROCESSED",
            event=event,
            cycle=cycle,
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
        prior=self.history(
            business_id=business_id,
            event_type="ANGEL_RESPONSE",
            mission_id=correction_id.strip(),
        )
        if any("OMAR.OWNER-INPUT" in event.angel_ids for event in prior):
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
            learning=learning,
            correction_id=correction_id.strip(),
            correction_memory=self.correction_memory,
        )
        return OmarCloseResult(
            processed=True,
            reason="OWNER_CORRECTION_PROCESSED",
            event=event,
            cycle=cycle,
        )
