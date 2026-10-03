"""Executable fail-closed gates for ZION CORE mission admission."""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class GateResult:
    gate: str
    allowed: bool
    reason: str

@dataclass(frozen=True)
class SecurityContext:
    authenticated: bool
    principal_id: str | None = None
    allowed_business_ids: tuple[str, ...] = ()
    human_approval_granted: bool = False
    production_write_allowed: bool = False

def seraphim(mission: dict[str, Any], context_refs: tuple[str, ...]) -> GateResult:
    if not context_refs:
        return GateResult("SERAPHIM", False, "CANONICAL_CONTEXT_MISSING")
    if mission.get("integrity_conflict") is True:
        return GateResult("SERAPHIM", False, "INTEGRITY_CONFLICT")
    return GateResult("SERAPHIM", True, "INTEGRITY_OK")

def cherubim(mission: dict[str, Any], isolation_key: str, security: SecurityContext | None) -> GateResult:
    requested_isolation = mission.get("isolation_key")
    if requested_isolation is not None and requested_isolation != isolation_key:
        return GateResult("CHERUBIM", False, "ISOLATION_BOUNDARY_VIOLATION")
    if security is None:
        return GateResult("CHERUBIM", True, "BOUNDARY_OK")
    if (security.authenticated is not True or not isinstance(security.principal_id,str)
            or not security.principal_id.strip()):
        return GateResult("CHERUBIM", False, "AUTHENTICATION_REQUIRED")
    if mission["business_id"] not in security.allowed_business_ids:
        return GateResult("CHERUBIM", False, "BUSINESS_ACCESS_DENIED")
    return GateResult("CHERUBIM", True, "BOUNDARY_OK")

def thrones(mission: dict[str, Any], security: SecurityContext | None) -> GateResult:
    if mission.get("policy_conflict") is True:
        return GateResult("THRONES", False, "POLICY_CONFLICT")
    if mission.get("human_approval_required") is True:
        if security is None or not security.human_approval_granted:
            return GateResult("THRONES", False, "HUMAN_APPROVAL_REQUIRED")
    return GateResult("THRONES", True, "POLICY_OK")

def powers(mission: dict[str, Any]) -> GateResult:
    if mission.get("runtime_enabled") is False:
        return GateResult("POWERS", False, "RUNTIME_DISABLED")
    if mission.get("kill_switch") is True:
        return GateResult("POWERS", False, "KILL_SWITCH_ACTIVE")
    if mission.get("risk_level", "low") in {"high", "critical"}:
        return GateResult("POWERS", False, "RISK_GATE")
    return GateResult("POWERS", True, "RUNTIME_OK")

def evaluate_gates(mission: dict[str, Any], isolation_key: str, context_refs: tuple[str, ...],
                   security: SecurityContext | None = None) -> tuple[GateResult, ...]:
    return (
        seraphim(mission, context_refs),
        cherubim(mission, isolation_key, security),
        thrones(mission, security),
        powers(mission),
    )
