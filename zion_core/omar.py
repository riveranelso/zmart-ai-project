"""OMAR: stable application entrypoints for ZION CORE orchestration."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .apokrisis import Apokrisis, omar_close_and_learn
from .biblia import BibliaContext, retrieve_biblia


@dataclass(frozen=True)
class MissionContext:
    business_id: str
    biblia: BibliaContext

    @property
    def knowledge(self) -> str:
        return self.biblia.text


def prepare_mission(
    business_id: str,
    *,
    biblia_root: Path,
    registry_path: Path | None = None,
) -> MissionContext:
    """Load isolated canonical knowledge before OMAR dispatches a mission."""
    biblia=retrieve_biblia(
        business_id,
        root=biblia_root,
        registry_path=registry_path,
    )
    return MissionContext(business_id=business_id,biblia=biblia)


@dataclass(frozen=True)
class LearningIntent:
    scope_hint: str | None = None
    explicit_durable_instruction: bool = False
    repeated_correction: bool = False
    stable_workflow: bool = False
    locked_asset: bool = False
    active_campaign: bool = False
    existing_rule_candidates: tuple[str, ...] = ()
    conflict: bool = False
    auto_write: bool = True


def receive_apokrisis(
    response: Apokrisis,
    *,
    biblia_root: Path,
    registry_path: Path | None = None,
    cronicas_sink: Any = None,
    learning: LearningIntent | None = None,
):
    """Stable OMAR port for closing ANGEL work and running the learning cycle."""
    intent=learning or LearningIntent()
    return omar_close_and_learn(
        response,
        biblia_root=biblia_root,
        registry_path=registry_path,
        cronicas_sink=cronicas_sink,
        scope_hint=intent.scope_hint,
        explicit_durable_instruction=intent.explicit_durable_instruction,
        repeated_correction=intent.repeated_correction,
        stable_workflow=intent.stable_workflow,
        locked_asset=intent.locked_asset,
        active_campaign=intent.active_campaign,
        existing_rule_candidates=intent.existing_rule_candidates,
        conflict=intent.conflict,
        auto_write=intent.auto_write,
    )
