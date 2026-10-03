"""Runtime composition for OMAR using local persistence adapters.

This module wires existing ZION CORE ports together. It intentionally does not
select or configure production infrastructure.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .omar import (
    LearningIntent,
    dispatch_mission,
    receive_apokrisis,
    receive_owner_correction,
)
from .persistence import CronicasJsonlSink, PersistentCorrectionMemory


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
        return dispatch_mission(
            mission,
            biblia_root=self.biblia_root,
            routes_path=self.routes_path,
            registry_path=self.registry_path,
            cronicas_sink=self.cronicas_sink,
            security_context=security_context,
        )

    def close(self, response: Any, *, learning: LearningIntent | None = None):
        return receive_apokrisis(
            response,
            biblia_root=self.biblia_root,
            registry_path=self.registry_path,
            cronicas_sink=self.cronicas_sink,
            learning=learning,
        )

    def owner_correction(
        self,
        correction: str,
        *,
        business_id: str,
        learning: LearningIntent | None = None,
        correction_id: str = "owner-correction",
    ):
        return receive_owner_correction(
            correction,
            business_id=business_id,
            biblia_root=self.biblia_root,
            registry_path=self.registry_path,
            cronicas_sink=self.cronicas_sink,
            learning=learning,
            correction_id=correction_id,
            correction_memory=self.correction_memory,
        )
