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

from .antiphon import (
    AntiphonError,
    AntiphonResult,
    BrandResolution,
    Classification,
    NormalizedComment,
    PublishIntent,
    PublishResult,
    ReplyDraft,
    CTA_VARIANTS,
    HUMAN_REVIEW,
    MAIN_BRAIN,
    ROUTINE,
    classify_comment,
    draft_reply,
    intake_comment,
    process_comment,
    publish_reply,
    resolve_brand,
)

from .glossolalia import (
    GlossolaliaError,
    ChannelCapabilities,
    IntegrationConfig,
    MetaNormalizedEvent,
    MetaRouteDecision,
    MetaActionIntent,
    MetaActionResult,
    MetaProcessResult,
    CHANNEL_CAPABILITIES,
    CHANNEL_EVENTS,
    WHATSAPP,
    INSTAGRAM,
    FACEBOOK,
    SEND_WHATSAPP_MESSAGE,
    SEND_INSTAGRAM_DM,
    REPLY_INSTAGRAM_COMMENT,
    SEND_FACEBOOK_MESSAGE,
    REPLY_FACEBOOK_COMMENT,
    HOLD_FOR_HUMAN,
    validate_integration_config,
    resolve_integration,
    intake_meta_event,
    meta_event_fingerprint,
    load_brand_brain,
    route_meta_event,
    draft_meta_reply,
    build_action_intent,
    route_meta_action,
    process_meta_event,
)

from .paradosis import (
    ParadosisError,
    TenantBindingError,
    MissionPacket,
    ModuleRecord,
    PacketFreshness,
    MODULE_REGISTRY,
    CORE_MODULES,
    build_mission_packet,
    bind_tenant,
    check_packet_freshness,
    refresh_packet,
    packet_summary,
    repo_head,
    repo_branch,
)

__all__ += [
    "ParadosisError",
    "TenantBindingError",
    "MissionPacket",
    "ModuleRecord",
    "PacketFreshness",
    "MODULE_REGISTRY",
    "CORE_MODULES",
    "build_mission_packet",
    "bind_tenant",
    "check_packet_freshness",
    "refresh_packet",
    "packet_summary",
    "repo_head",
    "repo_branch",
]

from .batch import BatchItem, BatchPlan, BatchDispatchResult, PatternObservation, PatternCandidate, plan_batch, pending_items, dispatch_pending, assess_pattern_reuse

__all__ += ["BatchItem", "BatchPlan", "BatchDispatchResult", "PatternObservation", "PatternCandidate", "plan_batch", "pending_items", "dispatch_pending", "assess_pattern_reuse"]
