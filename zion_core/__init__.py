"""ZION CORE runtime primitives."""
from .allocator import DiatassoCommission, diatasso, AngelAssignment, allocate_angels
from .router import DispatchDecision, MissionValidationError, exapostello, route_mission
from .cronicas import CronicaEvent, CronicasMemorySink, cronicas_emit, cronicas_emit_apokrisis
from .apokrisis import Apokrisis, apokrisis, close_apokrisis, omar_close_and_learn
from .holy_ghost import (
    LearningSignal,
    LearningProposal,
    LearningDestination,
    PromotionDecision,
    LearningCycle,
    holy_ghost_receive,
    evaluate_learning,
    resolve_learning_destination,
    propose_biblia_promotion,
    prepare_learning_cycle,
    persist_learning_cycle,
)
from .grapho import GraphoResult, grapho_render, grapho_write
from .omar import MissionContext, OmarMissionDispatch, AngelExecutionContext, prepare_mission, dispatch_mission, execution_contexts, LearningIntent, receive_apokrisis, receive_owner_correction
from .biblia import BibliaDocument, BibliaContext, retrieve_biblia, SCOPE_PRECEDENCE
from .durability import DurabilityAssessment, assess_durability
from .correction_memory import CorrectionMemory, correction_fingerprint
from .persistence import CronicasJsonlSink, PersistentCorrectionMemory

__all__ = [
    "DiatassoCommission", "diatasso", "AngelAssignment", "allocate_angels",
    "DispatchDecision", "MissionValidationError", "exapostello", "route_mission",
    "CronicaEvent", "CronicasMemorySink", "cronicas_emit", "cronicas_emit_apokrisis",
    "Apokrisis", "apokrisis", "close_apokrisis", "omar_close_and_learn",
    "LearningSignal", "LearningProposal", "LearningDestination", "PromotionDecision",
    "LearningCycle", "holy_ghost_receive", "evaluate_learning",
    "resolve_learning_destination", "propose_biblia_promotion",
    "prepare_learning_cycle", "persist_learning_cycle",
    "GraphoResult", "grapho_render", "grapho_write",
    "MissionContext", "OmarMissionDispatch", "AngelExecutionContext", "prepare_mission", "dispatch_mission", "execution_contexts", "LearningIntent", "receive_apokrisis", "receive_owner_correction",
    "BibliaDocument", "BibliaContext", "retrieve_biblia", "SCOPE_PRECEDENCE",
    "DurabilityAssessment", "assess_durability",
    "CorrectionMemory", "correction_fingerprint",
    "CronicasJsonlSink", "PersistentCorrectionMemory",
]

from .runtime import OmarRuntime, OmarCloseResult

from .persistence import CronicasReadError, read_cronicas
