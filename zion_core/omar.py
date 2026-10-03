"""OMAR: stable application entrypoints for ZION CORE orchestration."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .apokrisis import Apokrisis, omar_close_and_learn


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
