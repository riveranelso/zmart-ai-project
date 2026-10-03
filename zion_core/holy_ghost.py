"""HOLY GHOST learning signals derived from completed ANGEL work."""
from dataclasses import asdict, dataclass
from typing import Any

@dataclass(frozen=True)
class LearningSignal:
    mission_id: str
    angel_id: str
    business_id: str
    correlation_id: str | None
    needs_learning_review: bool
    uncertainty: tuple[str, ...]
    correction_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def holy_ghost_receive(response: Any) -> LearningSignal:
    """Create review evidence only. This function never mutates BIBLIA."""
    uncertainty = tuple(response.uncertainty)
    corrections = tuple(response.correction_signals)
    return LearningSignal(
        mission_id=str(response.mission_id),
        angel_id=str(response.angel_id),
        business_id=str(response.business_id),
        correlation_id=response.correlation_id,
        needs_learning_review=bool(uncertainty or corrections),
        uncertainty=uncertainty,
        correction_signals=corrections,
    )
