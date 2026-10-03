"""Deterministic durability signals for direct owner corrections."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class DurabilityAssessment:
    durable: bool
    reason: str


_EXPLICIT_PATTERNS=(
    r"\balways\b",
    r"\bfrom now on\b",
    r"\bevery time\b",
    r"\bpermanent(?:ly)?\b",
    r"\bsiempre\b",
    r"\bde ahora en adelante\b",
    r"\bcada vez\b",
    r"\bpermanente(?:mente)?\b",
    r"\bno vuelva a pasar\b",
    r"\bque no vuelva a pasar\b",
)


def assess_durability(
    correction: str,
    *,
    repeated_correction: bool = False,
    stable_workflow: bool = False,
    locked_asset: bool = False,
) -> DurabilityAssessment:
    """Classify only strong deterministic durability evidence; ambiguity stays temporary."""
    if not isinstance(correction,str) or not correction.strip():
        return DurabilityAssessment(False,"EMPTY_CORRECTION")
    if locked_asset:
        return DurabilityAssessment(True,"LOCKED_ASSET")
    if repeated_correction:
        return DurabilityAssessment(True,"REPEATED_CORRECTION")
    if stable_workflow:
        return DurabilityAssessment(True,"STABLE_WORKFLOW")
    text=correction.casefold()
    if any(re.search(pattern,text,re.IGNORECASE) for pattern in _EXPLICIT_PATTERNS):
        return DurabilityAssessment(True,"EXPLICIT_DURABLE_LANGUAGE")
    return DurabilityAssessment(False,"AMBIGUOUS_OR_ONE_OFF")
