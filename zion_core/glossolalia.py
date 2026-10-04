"""GLOSSOLALIA: Meta channel adapter layer inside ZION CORE.

Canonical naming record (per zmart360/BIBLIA/GLOBAL.md naming law):
  1. Technical function: receive Meta events (WhatsApp / Instagram /
     Facebook) in each channel's native "tongue", normalize them into one
     canonical ZION event; take one canonical ZION action intent and render
     it into the correct channel-specific call shape.
  2. Tradition searched: Christian (New Testament).
  3. Source: Greek glossolalia (glossolalia), "speaking in tongues" --
     the Pentecost phenomenon (Acts 2) where one message is heard in many
     tongues; the "interpretation of tongues" (1 Cor 12:10) is the
     interpretive gift between them.
  4. Correspondence: many channel tongues in, one canonical event out; one
     canonical intent in, the channel's tongue out. Interpretation between
     tongues is exactly the adapter's function.
  5. Respectful functional metaphor; no claim of absolute truth.

Canonical principle:
  ZION decides what to say.
  Brand Brain decides voice / brand rules.
  GLOSSOLALIA knows how to receive and send correctly per channel.

Architecture:
  META (whatsapp | instagram | facebook)
      -> CHANNEL INGEST -> NORMALIZE META EVENT -> RESOLVE INTEGRATION
      -> FIX business_id / brand_id -> LOAD BRAND BRAIN
      -> ZION (ROUTINE | MAIN_BRAIN | HUMAN_REVIEW)
      -> META ACTION ROUTER -> HOLD FOR HUMAN | TRANSPORT INTENT

Design notes:
  - Deterministic and pure: no network, no Meta API calls. Transport lives
    OUTSIDE ZION. GLOSSOLALIA emits transport-ready intents only.
  - Reuses (never duplicates): antiphon intake/classify/draft/write-gate
    patterns for text events, sanpedro_resolve for tenant isolation,
    prepare_mission/retrieve_biblia for Brand Brain loading,
    correction_fingerprint for event dedupe, CronicaEvent-shaped decision
    records for logging, SecurityContext.production_write_allowed as the
    write-gate abstraction (META_WRITE_ENABLED maps onto it).
  - The integration config FIXES business_id / brand_id / channel identity.
    External event identity can NEVER override them. Any mismatch fails
    closed.
  - No secrets in repo: credential_ref / webhook_verify_ref must be
    references (scheme: "env:...", "vault:...", "secret:..."), never raw
    tokens. Raw-looking values are rejected at config validation.
  - Write stages are separated: READ -> NORMALIZE -> ROUTE -> DRAFT ->
    ACTION -> WRITE. Having credentials never implies publish permission.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import antiphon
from .correction_memory import correction_fingerprint
from .gates import SecurityContext
from .omar import MissionContext, prepare_mission
from .registry import SanPedroError

# ---------------------------------------------------------------------------
# Channels, event types, actions
# ---------------------------------------------------------------------------

WHATSAPP = "whatsapp"
INSTAGRAM = "instagram"
FACEBOOK = "facebook"
CHANNELS = (WHATSAPP, INSTAGRAM, FACEBOOK)
PLATFORM = "meta"

WHATSAPP_EVENTS = ("inbound_message", "reply", "media_message", "status_event")
INSTAGRAM_EVENTS = ("dm", "dm_reply", "comment", "comment_reply")
FACEBOOK_EVENTS = ("messenger_message", "messenger_reply", "comment", "comment_reply")
CHANNEL_EVENTS: dict[str, tuple[str, ...]] = {
    WHATSAPP: WHATSAPP_EVENTS,
    INSTAGRAM: INSTAGRAM_EVENTS,
    FACEBOOK: FACEBOOK_EVENTS,
}

SEND_WHATSAPP_MESSAGE = "send_whatsapp_message"
SEND_INSTAGRAM_DM = "send_instagram_dm"
REPLY_INSTAGRAM_COMMENT = "reply_instagram_comment"
SEND_FACEBOOK_MESSAGE = "send_facebook_message"
REPLY_FACEBOOK_COMMENT = "reply_facebook_comment"
HOLD_FOR_HUMAN = "hold_for_human"
ACTIONS = (
    SEND_WHATSAPP_MESSAGE,
    SEND_INSTAGRAM_DM,
    REPLY_INSTAGRAM_COMMENT,
    SEND_FACEBOOK_MESSAGE,
    REPLY_FACEBOOK_COMMENT,
    HOLD_FOR_HUMAN,
)

# Text-bearing event types (routable through brand text classification).
_TEXT_EVENTS = (
    "inbound_message", "reply",
    "dm", "dm_reply", "comment", "comment_reply",
    "messenger_message", "messenger_reply",
)


class GlossolaliaError(ValueError):
    """Rejected Meta payload, config, or adapter misuse."""


# ---------------------------------------------------------------------------
# Channel capabilities (real per-channel differences, modeled not assumed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChannelCapabilities:
    channel: str
    allowed_actions: tuple[str, ...]
    # action -> event types it may answer
    action_event_map: dict[str, tuple[str, ...]]
    requires_conversation_id: tuple[str, ...]
    requires_parent_id: tuple[str, ...]
    supports_media: bool
    messaging_window_hours: int | None  # None = no enforced window modeled
    notes: tuple[str, ...] = ()


CHANNEL_CAPABILITIES: dict[str, ChannelCapabilities] = {
    WHATSAPP: ChannelCapabilities(
        channel=WHATSAPP,
        allowed_actions=(SEND_WHATSAPP_MESSAGE,),
        action_event_map={
            SEND_WHATSAPP_MESSAGE: ("inbound_message", "reply", "media_message"),
        },
        requires_conversation_id=(SEND_WHATSAPP_MESSAGE,),
        requires_parent_id=(),
        supports_media=True,
        messaging_window_hours=24,
        notes=(
            "Business-initiated messages outside the 24h window require a "
            "template; user-initiated threads do not.",
            "Replies reference the inbound message id as context.",
        ),
    ),
    INSTAGRAM: ChannelCapabilities(
        channel=INSTAGRAM,
        allowed_actions=(SEND_INSTAGRAM_DM, REPLY_INSTAGRAM_COMMENT),
        action_event_map={
            SEND_INSTAGRAM_DM: ("dm", "dm_reply"),
            REPLY_INSTAGRAM_COMMENT: ("comment", "comment_reply"),
        },
        requires_conversation_id=(SEND_INSTAGRAM_DM,),
        requires_parent_id=(REPLY_INSTAGRAM_COMMENT,),
        supports_media=True,
        messaging_window_hours=None,
        notes=(
            "DMs and comment replies are different surfaces; never answer a "
            "comment with a DM or vice versa.",
            "Comment replies require the parent comment id.",
        ),
    ),
    FACEBOOK: ChannelCapabilities(
        channel=FACEBOOK,
        allowed_actions=(SEND_FACEBOOK_MESSAGE, REPLY_FACEBOOK_COMMENT),
        action_event_map={
            SEND_FACEBOOK_MESSAGE: ("messenger_message", "messenger_reply"),
            REPLY_FACEBOOK_COMMENT: ("comment", "comment_reply"),
        },
        requires_conversation_id=(SEND_FACEBOOK_MESSAGE,),
        requires_parent_id=(REPLY_FACEBOOK_COMMENT,),
        supports_media=True,
        messaging_window_hours=24,
        notes=(
            "Messenger follows the 24h standard messaging window.",
            "Comment replies require the parent comment id.",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Integration config (no secrets -- references only)
# ---------------------------------------------------------------------------

_REF_SCHEMES = ("env:", "vault:", "secret:", "config:")


def _is_reference(value: str) -> bool:
    return any(value.startswith(s) for s in _REF_SCHEMES)


def _looks_like_raw_secret(value: str) -> bool:
    if _is_reference(value):
        return False
    # Long opaque token-shaped strings without a reference scheme.
    return bool(re.fullmatch(r"[A-Za-z0-9+/=_-]{32,}", value))


@dataclass(frozen=True)
class IntegrationConfig:
    integration_id: str
    business_id: str
    brand_id: str
    provider: str
    channel: str
    account_ref: str | None = None
    page_id: str | None = None
    instagram_account_id: str | None = None
    whatsapp_phone_number_id: str | None = None
    enabled: bool = True
    read_enabled: bool = True
    write_enabled: bool = False
    credential_ref: str | None = None
    webhook_verify_ref: str | None = None
    allowed_event_types: tuple[str, ...] = ()
    allowed_action_types: tuple[str, ...] = ()


def _req_str(cfg: dict[str, Any], key: str) -> str:
    value = cfg.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GlossolaliaError(f"INTEGRATION_FIELD_REQUIRED:{key}")
    return value.strip()


def validate_integration_config(cfg: dict[str, Any]) -> IntegrationConfig:
    """Validate an integration config dict. Rejects raw secrets."""
    if not isinstance(cfg, dict):
        raise GlossolaliaError("INTEGRATION_CONFIG_OBJECT_REQUIRED")
    integration_id = _req_str(cfg, "integration_id")
    business_id = _req_str(cfg, "business_id")
    brand_id = _req_str(cfg, "brand_id")
    provider = cfg.get("provider", "meta")
    if provider != "meta":
        raise GlossolaliaError("INTEGRATION_PROVIDER_MUST_BE_META")
    channel = _req_str(cfg, "channel")
    if channel not in CHANNELS:
        raise GlossolaliaError(f"INTEGRATION_UNKNOWN_CHANNEL:{channel}")
    for ref_key in ("credential_ref", "webhook_verify_ref"):
        ref = cfg.get(ref_key)
        if ref is None:
            continue
        if not isinstance(ref, str) or not ref.strip():
            raise GlossolaliaError(f"INTEGRATION_FIELD_INVALID:{ref_key}")
        ref = ref.strip()
        if _looks_like_raw_secret(ref):
            raise GlossolaliaError(f"INTEGRATION_RAW_SECRET_REJECTED:{ref_key}")
        if not _is_reference(ref):
            raise GlossolaliaError(f"INTEGRATION_REF_MUST_HAVE_SCHEME:{ref_key}")
    # Channel identity: each channel fixes its own identity field.
    identities = {
        "account_ref": cfg.get("account_ref"),
        "page_id": cfg.get("page_id"),
        "instagram_account_id": cfg.get("instagram_account_id"),
        "whatsapp_phone_number_id": cfg.get("whatsapp_phone_number_id"),
    }
    if channel == WHATSAPP and not identities["whatsapp_phone_number_id"]:
        raise GlossolaliaError("INTEGRATION_WHATSAPP_IDENTITY_REQUIRED")
    if channel == INSTAGRAM and not identities["instagram_account_id"]:
        raise GlossolaliaError("INTEGRATION_INSTAGRAM_IDENTITY_REQUIRED")
    if channel == FACEBOOK and not identities["page_id"]:
        raise GlossolaliaError("INTEGRATION_FACEBOOK_IDENTITY_REQUIRED")
    allowed_events = tuple(cfg.get("allowed_event_types") or ())
    for evt in allowed_events:
        if evt not in CHANNEL_EVENTS[channel]:
            raise GlossolaliaError(f"INTEGRATION_EVENT_NOT_FOR_CHANNEL:{evt}")
    allowed_actions = tuple(cfg.get("allowed_action_types") or ())
    for action in allowed_actions:
        if action not in CHANNEL_CAPABILITIES[channel].allowed_actions and action != HOLD_FOR_HUMAN:
            raise GlossolaliaError(f"INTEGRATION_ACTION_NOT_FOR_CHANNEL:{action}")

    def _opt(key: str) -> str | None:
        v = cfg.get(key)
        return v.strip() if isinstance(v, str) and v.strip() else None

    return IntegrationConfig(
        integration_id=integration_id,
        business_id=business_id,
        brand_id=brand_id,
        provider="meta",
        channel=channel,
        account_ref=_opt("account_ref"),
        page_id=_opt("page_id"),
        instagram_account_id=_opt("instagram_account_id"),
        whatsapp_phone_number_id=_opt("whatsapp_phone_number_id"),
        enabled=bool(cfg.get("enabled", True)),
        read_enabled=bool(cfg.get("read_enabled", True)),
        write_enabled=bool(cfg.get("write_enabled", False)),
        credential_ref=_opt("credential_ref"),
        webhook_verify_ref=_opt("webhook_verify_ref"),
        allowed_event_types=allowed_events,
        allowed_action_types=allowed_actions,
    )


# ---------------------------------------------------------------------------
# Normalized Meta event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetaNormalizedEvent:
    platform: str
    channel: str
    event_type: str
    business_id_internal: str
    brand_id_internal: str
    integration_id: str
    sender_id: str
    conversation_id: str | None
    message_id: str
    parent_id: str | None
    thread_id: str | None
    text: str | None
    media_refs: tuple[str, ...]
    timestamp: str | None
    raw_event_ref: str | None


def _raw_str(raw: dict[str, Any], key: str, required: bool = True) -> str | None:
    value = raw.get(key)
    if value is None:
        if required:
            raise GlossolaliaError(f"META_FIELD_REQUIRED:{key}")
        return None
    if not isinstance(value, str) or not value.strip():
        raise GlossolaliaError(f"META_FIELD_INVALID:{key}")
    return value.strip()


def resolve_integration(
    event_identity: dict[str, Any],
    configs: list[IntegrationConfig],
) -> IntegrationConfig:
    """Resolve which integration owns an inbound event. Fail closed.

    Matches on (channel, channel identity). The integration's fixed
    business_id/brand_id can never be overridden by the event payload.
    """
    if not isinstance(event_identity, dict):
        raise GlossolaliaError("EVENT_IDENTITY_OBJECT_REQUIRED")
    channel = event_identity.get("channel")
    if channel not in CHANNELS:
        raise GlossolaliaError(f"UNKNOWN_CHANNEL:{channel}")
    identity_value = event_identity.get("identity")
    if not isinstance(identity_value, str) or not identity_value.strip():
        raise GlossolaliaError("EVENT_IDENTITY_REQUIRED")
    identity_value = identity_value.strip()
    candidates = [
        c for c in configs
        if c.channel == channel and (
            c.account_ref == identity_value
            or c.page_id == identity_value
            or c.instagram_account_id == identity_value
            or c.whatsapp_phone_number_id == identity_value
        )
    ]
    if not candidates:
        raise GlossolaliaError("INTEGRATION_NOT_FOUND")
    if len(candidates) > 1:
        raise GlossolaliaError("INTEGRATION_IDENTITY_AMBIGUOUS")
    config = candidates[0]
    if not config.enabled:
        raise GlossolaliaError("INTEGRATION_DISABLED")
    if not config.read_enabled:
        raise GlossolaliaError("INTEGRATION_READ_DISABLED")
    # Claimed business/brand in the payload must equal the integration's
    # fixed values; mismatch fails closed and never overrides.
    for key in ("business_id", "brand_id"):
        claimed = event_identity.get(key)
        fixed = getattr(config, key)
        if claimed is not None and claimed != fixed:
            raise GlossolaliaError(f"TENANT_MISMATCH:{key}")
    return config


def intake_meta_event(
    raw: dict[str, Any], integration: IntegrationConfig
) -> MetaNormalizedEvent:
    """CHANNEL INGEST + NORMALIZE. Pure; no network.

    business_id/brand_id are FIXED from the integration, never from payload.
    """
    if not isinstance(raw, dict):
        raise GlossolaliaError("META_PAYLOAD_OBJECT_REQUIRED")
    channel = _raw_str(raw, "channel")
    if channel != integration.channel:
        raise GlossolaliaError("META_CHANNEL_INTEGRATION_MISMATCH")
    event_type = _raw_str(raw, "event_type")
    if event_type not in CHANNEL_EVENTS[channel]:
        raise GlossolaliaError(f"META_EVENT_NOT_FOR_CHANNEL:{event_type}")
    if integration.allowed_event_types and event_type not in integration.allowed_event_types:
        raise GlossolaliaError(f"META_EVENT_NOT_ALLOWED:{event_type}")
    media_refs = raw.get("media_refs") or ()
    if not isinstance(media_refs, (list, tuple)) or any(
        not isinstance(m, str) for m in media_refs
    ):
        raise GlossolaliaError("META_FIELD_INVALID:media_refs")
    text = raw.get("text")
    if text is not None and (not isinstance(text, str) or not text.strip()):
        raise GlossolaliaError("META_FIELD_INVALID:text")
    return MetaNormalizedEvent(
        platform=PLATFORM,
        channel=channel,
        event_type=event_type,
        business_id_internal=integration.business_id,
        brand_id_internal=integration.brand_id,
        integration_id=integration.integration_id,
        sender_id=_raw_str(raw, "sender_id"),
        conversation_id=_raw_str(raw, "conversation_id", required=False),
        message_id=_raw_str(raw, "message_id"),
        parent_id=_raw_str(raw, "parent_id", required=False),
        thread_id=_raw_str(raw, "thread_id", required=False),
        text=text.strip() if isinstance(text, str) else None,
        media_refs=tuple(media_refs),
        timestamp=_raw_str(raw, "timestamp", required=False),
        raw_event_ref=_raw_str(raw, "raw_event_ref", required=False),
    )


def meta_event_fingerprint(event: MetaNormalizedEvent) -> str:
    """Deterministic dedupe fingerprint (reuses correction_fingerprint style)."""
    basis = "|".join((
        event.platform, event.channel, event.event_type,
        event.business_id_internal, event.message_id,
        event.sender_id, event.conversation_id or "",
        event.timestamp or "", (event.text or "")[:500],
    ))
    return correction_fingerprint(basis)


# ---------------------------------------------------------------------------
# Brand Brain loading + ZION routing (reuses antiphon for text events)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetaRouteDecision:
    route: str  # ROUTINE | MAIN_BRAIN | HUMAN_REVIEW
    subtype: str
    reasons: tuple[str, ...]
    draftable: bool
    brand_resolved: bool


def load_brand_brain(
    event: MetaNormalizedEvent,
    *,
    biblia_root: Path,
    registry_path: Path | None = None,
) -> MissionContext:
    """LOAD BRAND BRAIN: isolated canonical knowledge for the event's brand."""
    return prepare_mission(
        event.business_id_internal,
        biblia_root=biblia_root,
        registry_path=registry_path,
        mission_id=f"meta-{event.message_id}",
        scope=f"meta:{event.channel}:{event.event_type}",
        payload_ref=event.raw_event_ref,
    )


def _as_antiphon_comment(event: MetaNormalizedEvent) -> antiphon.NormalizedComment:
    """Adapt a Meta text event to antiphon's brand text router (reuse)."""
    return antiphon.NormalizedComment(
        comment_id=event.message_id,
        video_id=event.conversation_id or event.parent_id or event.message_id,
        author=event.sender_id,
        text=event.text or "",
        business_id=event.business_id_internal,
        channel_id=None,
        author_channel_id=None,
        published_at=event.timestamp,
        like_count=0,
        video_title=None,
        video_artist=None,
        truncated=False,
    )


def route_meta_event(
    event: MetaNormalizedEvent,
    *,
    registry_path: Path | None = None,
) -> MetaRouteDecision:
    """ZION routing for a normalized Meta event.

    Text-bearing events reuse antiphon's canonical brand classification
    (no duplicated logic). Non-text events route by type:
      - media without text -> MAIN_BRAIN (cannot interpret media
        deterministically);
      - status_event -> ROUTINE, not draftable (informational only).
    """
    brand = antiphon.resolve_brand(
        antiphon.NormalizedComment(
            comment_id=event.message_id,
            video_id=event.message_id,
            author=event.sender_id,
            text=event.text or "x",
            business_id=event.business_id_internal,
        ),
        registry_path,
    )
    if not brand.resolved:
        return MetaRouteDecision(
            route=antiphon.HUMAN_REVIEW, subtype="brand_unresolved",
            reasons=(brand.reason,), draftable=False, brand_resolved=False,
        )
    if event.event_type == "status_event":
        return MetaRouteDecision(
            route=antiphon.ROUTINE, subtype="status_event",
            reasons=("INFORMATIONAL_NO_REPLY",), draftable=False,
            brand_resolved=True,
        )
    if event.event_type in _TEXT_EVENTS and event.text:
        classification = antiphon.classify_comment(_as_antiphon_comment(event))
        return MetaRouteDecision(
            route=classification.route, subtype=classification.subtype,
            reasons=classification.reasons,
            draftable=classification.route == antiphon.ROUTINE,
            brand_resolved=True,
        )
    return MetaRouteDecision(
        route=antiphon.MAIN_BRAIN, subtype="insufficient_context",
        reasons=("NO_TEXT_CONTENT",), draftable=False, brand_resolved=True,
    )


def draft_meta_reply(
    event: MetaNormalizedEvent,
    decision: MetaRouteDecision,
    *,
    registry_path: Path | None = None,
) -> antiphon.ReplyDraft | None:
    """Draft a brand-voiced reply for ROUTINE text events (reuses antiphon)."""
    if not decision.draftable or decision.route != antiphon.ROUTINE:
        return None
    comment = _as_antiphon_comment(event)
    brand = antiphon.resolve_brand(comment, registry_path)
    classification = antiphon.classify_comment(comment)
    return antiphon.draft_reply(comment, classification, brand=brand)


# ---------------------------------------------------------------------------
# Meta action router (intent only -- no transport)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetaActionIntent:
    action: str
    channel: str
    integration_id: str
    business_id: str
    conversation_id: str | None
    parent_id: str | None
    text: str
    event_fingerprint: str
    idempotency_key: str


@dataclass(frozen=True)
class MetaActionResult:
    status: str  # TRANSPORT_INTENT | DRAFT_ONLY | HELD_FOR_HUMAN |
    # HELD_MAIN_BRAIN | REJECTED
    reason: str
    intent: MetaActionIntent | None = None


def _default_action_for(channel: str, event_type: str) -> str:
    caps = CHANNEL_CAPABILITIES[channel]
    if channel == WHATSAPP:
        return SEND_WHATSAPP_MESSAGE
    if channel == INSTAGRAM:
        return SEND_INSTAGRAM_DM if event_type in ("dm", "dm_reply") else REPLY_INSTAGRAM_COMMENT
    return SEND_FACEBOOK_MESSAGE if event_type in ("messenger_message", "messenger_reply") else REPLY_FACEBOOK_COMMENT


def build_action_intent(
    event: MetaNormalizedEvent,
    draft: antiphon.ReplyDraft,
    *,
    integration: IntegrationConfig,
    action: str | None = None,
) -> MetaActionIntent:
    """Build a channel-validated action intent. Fail safe on mismatch.

    ZION never calls Meta endpoints; this intent is the transport contract
    the Meta adapter (external) executes.
    """
    if draft.business_id != event.business_id_internal:
        raise GlossolaliaError("ACTION_CROSS_BUSINESS")
    action = action or _default_action_for(event.channel, event.event_type)
    caps = CHANNEL_CAPABILITIES[event.channel]
    if action not in caps.allowed_actions:
        raise GlossolaliaError(f"ACTION_NOT_FOR_CHANNEL:{action}")
    if event.event_type not in caps.action_event_map[action]:
        raise GlossolaliaError(f"ACTION_NOT_FOR_EVENT:{action}:{event.event_type}")
    if integration.allowed_action_types and action not in integration.allowed_action_types:
        raise GlossolaliaError(f"ACTION_NOT_ALLOWED_BY_INTEGRATION:{action}")
    if action in caps.requires_conversation_id and not event.conversation_id:
        raise GlossolaliaError(f"ACTION_REQUIRES_CONVERSATION:{action}")
    if action in caps.requires_parent_id and not event.parent_id:
        # Comment replies need the parent comment id; without it, fail safe.
        raise GlossolaliaError(f"ACTION_REQUIRES_PARENT:{action}")
    fingerprint = meta_event_fingerprint(event)
    return MetaActionIntent(
        action=action,
        channel=event.channel,
        integration_id=integration.integration_id,
        business_id=event.business_id_internal,
        conversation_id=event.conversation_id,
        parent_id=event.parent_id,
        text=draft.text,
        event_fingerprint=fingerprint,
        idempotency_key=fingerprint,
    )


def route_meta_action(
    intent: MetaActionIntent,
    decision: MetaRouteDecision,
    *,
    integration: IntegrationConfig,
    security: SecurityContext | None = None,
    meta_write_enabled: bool = False,
) -> MetaActionResult:
    """META ACTION ROUTER with separated write gates.

    READ -> NORMALIZE -> ROUTE -> DRAFT -> ACTION -> WRITE are distinct
    stages. Write requires ALL of: meta_write_enabled=True,
    integration.write_enabled=True, security.production_write_allowed=True.
    Having credentials never implies publish permission.
      - HUMAN_REVIEW: never auto-publishes -> HELD_FOR_HUMAN.
      - MAIN_BRAIN: not eligible until resolved -> HELD_MAIN_BRAIN.
      - ROUTINE + write off -> DRAFT_ONLY (intent recorded, nothing sent).
      - ROUTINE + write on -> TRANSPORT_INTENT (no HTTP performed here).
    """
    if intent.business_id != integration.business_id:
        return MetaActionResult(status="REJECTED", reason="INTENT_INTEGRATION_BUSINESS_MISMATCH")
    if decision.route == antiphon.HUMAN_REVIEW:
        return MetaActionResult(status="HELD_FOR_HUMAN", reason="ROUTE_HUMAN_REVIEW", intent=intent)
    if decision.route == antiphon.MAIN_BRAIN:
        return MetaActionResult(status="HELD_MAIN_BRAIN", reason="ROUTE_MAIN_BRAIN_NOT_ELIGIBLE", intent=intent)
    write_gate = (
        meta_write_enabled is True
        and integration.write_enabled is True
        and security is not None
        and security.production_write_allowed is True
    )
    if not write_gate:
        return MetaActionResult(status="DRAFT_ONLY", reason="WRITE_GATE_DISABLED", intent=intent)
    return MetaActionResult(status="TRANSPORT_INTENT", reason="WRITE_GATE_OPEN", intent=intent)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetaProcessResult:
    event: MetaNormalizedEvent
    fingerprint: str
    duplicate: bool
    brand_brain: MissionContext | None
    decision: MetaRouteDecision
    draft: antiphon.ReplyDraft | None
    action: MetaActionResult | None
    decision_log: dict[str, Any] = field(default_factory=dict)


def process_meta_event(
    raw: dict[str, Any],
    *,
    integration: IntegrationConfig,
    biblia_root: Path | None = None,
    registry_path: Path | None = None,
    security: SecurityContext | None = None,
    meta_write_enabled: bool = False,
    seen_fingerprints: set[str] | None = None,
    attempt_action: bool = False,
    action: str | None = None,
) -> MetaProcessResult:
    """Run the full GLOSSOLALIA pipeline on one raw Meta payload.

    Stages stay separated; write defaults OFF; duplicates are idempotent;
    nothing is ever sent to Meta from here.
    """
    event = intake_meta_event(raw, integration)
    fingerprint = meta_event_fingerprint(event)
    if seen_fingerprints is not None and fingerprint in seen_fingerprints:
        return MetaProcessResult(
            event=event, fingerprint=fingerprint, duplicate=True,
            brand_brain=None,
            decision=MetaRouteDecision(
                route=antiphon.MAIN_BRAIN, subtype="duplicate",
                reasons=("EVENT_ALREADY_SEEN",), draftable=False,
                brand_resolved=True,
            ),
            draft=None, action=None,
            decision_log={"duplicate": True, "fingerprint": fingerprint},
        )
    if seen_fingerprints is not None:
        seen_fingerprints.add(fingerprint)
    brand_brain = None
    if biblia_root is not None:
        brand_brain = load_brand_brain(
            event, biblia_root=biblia_root, registry_path=registry_path
        )
    decision = route_meta_event(event, registry_path=registry_path)
    draft = draft_meta_reply(event, decision, registry_path=registry_path)
    action_result = None
    if attempt_action and draft is not None:
        intent = build_action_intent(
            event, draft, integration=integration, action=action
        )
        action_result = route_meta_action(
            intent, decision, integration=integration,
            security=security, meta_write_enabled=meta_write_enabled,
        )
    decision_log = {
        "platform": event.platform,
        "channel": event.channel,
        "event_type": event.event_type,
        "integration_id": event.integration_id,
        "business_id": event.business_id_internal,
        "fingerprint": fingerprint,
        "route": decision.route,
        "subtype": decision.subtype,
        "reasons": list(decision.reasons),
        "drafted": draft is not None,
        "action_status": action_result.status if action_result else None,
        "action_reason": action_result.reason if action_result else None,
    }
    return MetaProcessResult(
        event=event, fingerprint=fingerprint, duplicate=False,
        brand_brain=brand_brain, decision=decision, draft=draft,
        action=action_result, decision_log=decision_log,
    )
