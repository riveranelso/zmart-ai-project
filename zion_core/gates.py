"""Executable fail-closed gates for ZION CORE mission admission."""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class GateResult:
    gate: str
    allowed: bool
    reason: str

def seraphim(mission: dict[str, Any], context_refs: tuple[str, ...]) -> GateResult:
    if not context_refs:
        return GateResult("SERAPHIM", False, "CANONICAL_CONTEXT_MISSING")
    if mission.get("integrity_conflict") is True:
        return GateResult("SERAPHIM", False, "INTEGRITY_CONFLICT")
    return GateResult("SERAPHIM", True, "INTEGRITY_OK")

def cherubim(mission: dict[str, Any], isolation_key: str) -> GateResult:
    requested = mission.get("isolation_key")
    if requested is not None and requested != isolation_key:
        return GateResult("CHERUBIM", False, "ISOLATION_BOUNDARY_VIOLATION")
    if mission.get("authorized") is False:
        return GateResult("CHERUBIM", False, "UNAUTHORIZED")
    return GateResult("CHERUBIM", True, "BOUNDARY_OK")

def thrones(mission: dict[str, Any]) -> GateResult:
    if mission.get("human_approval_required") is True:
        return GateResult("THRONES", False, "HUMAN_APPROVAL_REQUIRED")
    if mission.get("policy_conflict") is True:
        return GateResult("THRONES", False, "POLICY_CONFLICT")
    return GateResult("THRONES", True, "POLICY_OK")

def powers(mission: dict[str, Any]) -> GateResult:
    if mission.get("runtime_enabled") is False:
        return GateResult("POWERS", False, "RUNTIME_DISABLED")
    if mission.get("risk_level", "low") in {"high", "critical"}:
        return GateResult("POWERS", False, "RISK_GATE")
    if mission.get("kill_switch") is True:
        return GateResult("POWERS", False, "KILL_SWITCH_ACTIVE")
    return GateResult("POWERS", True, "RUNTIME_OK")

def evaluate_gates(mission: dict[str, Any], isolation_key: str,
                   context_refs: tuple[str, ...]) -> tuple[GateResult, ...]:
    results = (
        seraphim(mission, context_refs),
        cherubim(mission, isolation_key),
        thrones(mission),
        powers(mission),
    )
    return results
