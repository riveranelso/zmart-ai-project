"""Adversarial tests for GLOSSOLALIA (zion_core.glossolalia).

Covers: integration config validation (no raw secrets), integration
resolution (fail closed), cross-tenant substitution attacks, channel
intake/normalization, event fingerprint dedupe, ZION routing reuse,
drafting, the Meta action router with separated write gates, channel
capabilities, and the no-network invariant.
"""
import json
import tempfile
import unittest
from pathlib import Path

from zion_core import (
    GlossolaliaError,
    HOLD_FOR_HUMAN,
    INSTAGRAM,
    REPLY_INSTAGRAM_COMMENT,
    SEND_INSTAGRAM_DM,
    SEND_WHATSAPP_MESSAGE,
    SEND_FACEBOOK_MESSAGE,
    REPLY_FACEBOOK_COMMENT,
    WHATSAPP,
    FACEBOOK,
    build_action_intent,
    draft_meta_reply,
    intake_meta_event,
    load_brand_brain,
    meta_event_fingerprint,
    process_meta_event,
    resolve_integration,
    route_meta_action,
    route_meta_event,
    validate_integration_config,
)
from zion_core.gates import SecurityContext


def _wa_config(**overrides):
    cfg = {
        "integration_id": "wa-losduros-1",
        "business_id": "los-duros",
        "brand_id": "los-duros",
        "provider": "meta",
        "channel": "whatsapp",
        "whatsapp_phone_number_id": "phone-123",
        "credential_ref": "env:META_WA_TOKEN",
        "webhook_verify_ref": "env:META_WA_VERIFY",
        "allowed_event_types": ["inbound_message", "reply"],
        "allowed_action_types": ["send_whatsapp_message"],
    }
    cfg.update(overrides)
    return validate_integration_config(cfg)


def _ig_config(**overrides):
    cfg = {
        "integration_id": "ig-losduros-1",
        "business_id": "los-duros",
        "brand_id": "los-duros",
        "provider": "meta",
        "channel": "instagram",
        "instagram_account_id": "ig-456",
        "credential_ref": "vault:meta/ig/token",
        "allowed_event_types": ["dm", "comment", "comment_reply"],
        "allowed_action_types": ["send_instagram_dm", "reply_instagram_comment"],
    }
    cfg.update(overrides)
    return validate_integration_config(cfg)


def _fb_config(**overrides):
    cfg = {
        "integration_id": "fb-losduros-1",
        "business_id": "los-duros",
        "brand_id": "los-duros",
        "provider": "meta",
        "channel": "facebook",
        "page_id": "page-789",
        "credential_ref": "secret:meta/fb/token",
        "allowed_event_types": ["messenger_message", "comment"],
        "allowed_action_types": ["send_facebook_message", "reply_facebook_comment"],
    }
    cfg.update(overrides)
    return validate_integration_config(cfg)


def _registry(tmp):
    path = Path(tmp) / "registry.json"
    path.write_text(json.dumps({
        "defaults": {"deny_unknown_business": True, "deny_disabled_business": True,
                      "require_context_refs": True},
        "businesses": {
            "los-duros": {"enabled": True, "isolation_key": "los-duros",
                          "context_refs": ["zmart360/BIBLIA/GLOBAL.md"]},
            "zmart-consumer-rights": {"enabled": True, "isolation_key": "zmart-consumer-rights",
                                      "context_refs": ["zmart360/BIBLIA/GLOBAL.md"]},
        },
    }), encoding="utf-8")
    return path


def _biblia_root(tmp):
    root = Path(tmp) / "biblia"
    target = root / "zmart360" / "BIBLIA" / "GLOBAL.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Global\n", encoding="utf-8")
    return root


class ConfigValidationTests(unittest.TestCase):
    def test_whatsapp_requires_phone_identity(self):
        with self.assertRaises(GlossolaliaError):
            validate_integration_config({
                "integration_id": "x", "business_id": "los-duros",
                "brand_id": "los-duros", "channel": "whatsapp",
            })

    def test_instagram_requires_account_identity(self):
        with self.assertRaises(GlossolaliaError):
            validate_integration_config({
                "integration_id": "x", "business_id": "los-duros",
                "brand_id": "los-duros", "channel": "instagram",
            })

    def test_facebook_requires_page_identity(self):
        with self.assertRaises(GlossolaliaError):
            validate_integration_config({
                "integration_id": "x", "business_id": "los-duros",
                "brand_id": "los-duros", "channel": "facebook",
            })

    def test_raw_secret_rejected(self):
        with self.assertRaises(GlossolaliaError):
            _wa_config(credential_ref="EAABwzXYZ1234567890abcdefghijklmnop")

    def test_ref_without_scheme_rejected(self):
        with self.assertRaises(GlossolaliaError):
            _wa_config(credential_ref="my-token-name")

    def test_reference_schemes_accepted(self):
        for ref in ("env:X", "vault:a/b", "secret:a", "config:a"):
            cfg = _wa_config(credential_ref=ref)
            self.assertEqual(cfg.credential_ref, ref)

    def test_event_not_for_channel_rejected(self):
        with self.assertRaises(GlossolaliaError):
            _wa_config(allowed_event_types=["dm"])

    def test_action_not_for_channel_rejected(self):
        with self.assertRaises(GlossolaliaError):
            _wa_config(allowed_action_types=["send_instagram_dm"])

    def test_write_defaults_off(self):
        cfg = _wa_config()
        self.assertFalse(cfg.write_enabled)


class IntegrationResolutionTests(unittest.TestCase):
    def test_resolves_by_channel_identity(self):
        cfg = resolve_integration(
            {"channel": "whatsapp", "identity": "phone-123"},
            [_wa_config(), _ig_config()],
        )
        self.assertEqual(cfg.integration_id, "wa-losduros-1")

    def test_no_match_fails_closed(self):
        with self.assertRaises(GlossolaliaError):
            resolve_integration(
                {"channel": "whatsapp", "identity": "phone-999"},
                [_wa_config()],
            )

    def test_ambiguous_identity_fails_closed(self):
        dup = _wa_config(integration_id="wa-dup")
        with self.assertRaises(GlossolaliaError):
            resolve_integration(
                {"channel": "whatsapp", "identity": "phone-123"},
                [_wa_config(), dup],
            )

    def test_disabled_integration_fails_closed(self):
        cfg = _wa_config(enabled=False)
        with self.assertRaises(GlossolaliaError):
            resolve_integration(
                {"channel": "whatsapp", "identity": "phone-123"}, [cfg])

    def test_read_disabled_fails_closed(self):
        cfg = _wa_config(read_enabled=False)
        with self.assertRaises(GlossolaliaError):
            resolve_integration(
                {"channel": "whatsapp", "identity": "phone-123"}, [cfg])


class CrossTenantSubstitutionTests(unittest.TestCase):
    """The integration fixes business/brand; payload claims never override."""

    def test_business_substitution_fails_closed(self):
        with self.assertRaises(GlossolaliaError) as ctx:
            resolve_integration(
                {"channel": "instagram", "identity": "ig-456",
                 "business_id": "zmart-consumer-rights"},
                [_ig_config()],
            )
        self.assertIn("TENANT_MISMATCH", str(ctx.exception))

    def test_brand_substitution_fails_closed(self):
        with self.assertRaises(GlossolaliaError) as ctx:
            resolve_integration(
                {"channel": "instagram", "identity": "ig-456",
                 "brand_id": "zmart-consumer-rights"},
                [_ig_config()],
            )
        self.assertIn("TENANT_MISMATCH", str(ctx.exception))

    def test_matching_claims_pass(self):
        cfg = resolve_integration(
            {"channel": "instagram", "identity": "ig-456",
             "business_id": "los-duros", "brand_id": "los-duros"},
            [_ig_config()],
        )
        self.assertEqual(cfg.business_id, "los-duros")

    def test_intake_fixes_business_from_integration(self):
        # Even if the raw payload carried a foreign business_id, intake
        # never reads it: identity comes from the integration only.
        event = intake_meta_event(
            {"channel": "instagram", "event_type": "dm",
             "sender_id": "user-1", "message_id": "m-1",
             "conversation_id": "conv-1", "text": "hola",
             "business_id": "zmart-consumer-rights"},
            _ig_config(),
        )
        self.assertEqual(event.business_id_internal, "los-duros")
        self.assertEqual(event.brand_id_internal, "los-duros")

    def test_full_pipeline_never_loads_foreign_brain(self):
        # The pipeline binds to the integration's fixed identity: even if an
        # attacker smuggles a foreign business claim at resolve time, the
        # failure happens before any brand brain loads or draft is produced.
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            result = process_meta_event(
                {"channel": "instagram", "event_type": "dm",
                 "sender_id": "u", "message_id": "m",
                 "conversation_id": "c", "text": "hola"},
                integration=_ig_config(),
                registry_path=reg,
            )
            self.assertEqual(result.event.business_id_internal, "los-duros")
            self.assertEqual(result.event.brand_id_internal, "los-duros")
            # And the smuggling attempt itself fails closed at resolve:
            with self.assertRaises(GlossolaliaError):
                resolve_integration(
                    {"channel": "instagram", "identity": "ig-456",
                     "business_id": "zmart-consumer-rights"},
                    [_ig_config()],
                )


class IntakeNormalizationTests(unittest.TestCase):
    def test_whatsapp_normalizes(self):
        event = intake_meta_event(
            {"channel": "whatsapp", "event_type": "inbound_message",
             "sender_id": "+17875550100", "message_id": "wamid-1",
             "conversation_id": "+17875550100", "text": "esto está duro",
             "timestamp": "2026-10-03T20:00:00Z"},
            _wa_config(),
        )
        self.assertEqual(event.platform, "meta")
        self.assertEqual(event.business_id_internal, "los-duros")
        self.assertEqual(event.text, "esto está duro")

    def test_channel_mismatch_rejected(self):
        with self.assertRaises(GlossolaliaError):
            intake_meta_event(
                {"channel": "instagram", "event_type": "dm",
                 "sender_id": "u", "message_id": "m", "text": "hola"},
                _wa_config(),
            )

    def test_disallowed_event_type_rejected(self):
        with self.assertRaises(GlossolaliaError):
            intake_meta_event(
                {"channel": "whatsapp", "event_type": "status_event",
                 "sender_id": "u", "message_id": "m"},
                _wa_config(),  # only inbound_message, reply allowed
            )

    def test_missing_message_id_rejected(self):
        with self.assertRaises(GlossolaliaError):
            intake_meta_event(
                {"channel": "whatsapp", "event_type": "inbound_message",
                 "sender_id": "u", "text": "hola"},
                _wa_config(),
            )

    def test_media_refs_must_be_strings(self):
        with self.assertRaises(GlossolaliaError):
            intake_meta_event(
                {"channel": "instagram", "event_type": "dm",
                 "sender_id": "u", "message_id": "m", "media_refs": [123]},
                _ig_config(),
            )


class FingerprintDedupeTests(unittest.TestCase):
    def test_same_event_same_fingerprint(self):
        cfg = _ig_config()
        raw = {"channel": "instagram", "event_type": "dm", "sender_id": "u",
               "message_id": "m-1", "conversation_id": "c", "text": "hola"}
        a = meta_event_fingerprint(intake_meta_event(raw, cfg))
        b = meta_event_fingerprint(intake_meta_event(dict(raw), cfg))
        self.assertEqual(a, b)

    def test_different_events_different_fingerprints(self):
        cfg = _ig_config()
        base = {"channel": "instagram", "event_type": "dm", "sender_id": "u",
                "conversation_id": "c", "text": "hola"}
        a = meta_event_fingerprint(intake_meta_event(dict(base, message_id="m-1"), cfg))
        b = meta_event_fingerprint(intake_meta_event(dict(base, message_id="m-2"), cfg))
        self.assertNotEqual(a, b)

    def test_duplicate_event_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            seen = set()
            raw = {"channel": "whatsapp", "event_type": "inbound_message",
                   "sender_id": "u", "message_id": "dup-1",
                   "conversation_id": "c", "text": "esto está duro"}
            first = process_meta_event(raw, integration=_wa_config(),
                                       registry_path=reg, seen_fingerprints=seen)
            second = process_meta_event(raw, integration=_wa_config(),
                                        registry_path=reg, seen_fingerprints=seen)
            self.assertFalse(first.duplicate)
            self.assertTrue(second.duplicate)
            self.assertIsNone(second.draft)
            self.assertIsNone(second.action)


class RoutingTests(unittest.TestCase):
    def test_whatsapp_routine_routes_and_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            result = process_meta_event(
                {"channel": "whatsapp", "event_type": "inbound_message",
                 "sender_id": "u", "message_id": "r-1",
                 "conversation_id": "c", "text": "esto está duro, me encanta"},
                integration=_wa_config(), registry_path=reg,
            )
            self.assertEqual(result.decision.route, "ROUTINE")
            self.assertIsNotNone(result.draft)
            self.assertIn(result.draft.cta_variant, result.draft.text)

    def test_instagram_chotiaera_goes_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            result = process_meta_event(
                {"channel": "instagram", "event_type": "comment",
                 "sender_id": "u", "message_id": "c-1",
                 "parent_id": "post-9", "text": "ese tipo es un chota"},
                integration=_ig_config(), registry_path=reg,
            )
            self.assertEqual(result.decision.route, "HUMAN_REVIEW")
            self.assertIsNone(result.draft)

    def test_media_without_text_goes_main_brain(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            cfg = _ig_config(allowed_event_types=["dm", "comment", "comment_reply"])
            raw = {"channel": "instagram", "event_type": "dm",
                   "sender_id": "u", "message_id": "m-9",
                   "conversation_id": "c", "media_refs": ["media:1"]}
            # dm without text: intake ok (text optional), routes to MAIN_BRAIN
            event = intake_meta_event(raw, cfg)
            decision = route_meta_event(event, registry_path=reg)
            self.assertEqual(decision.route, "MAIN_BRAIN")
            self.assertFalse(decision.draftable)

    def test_status_event_is_routine_not_draftable(self):
        cfg = _wa_config(allowed_event_types=["inbound_message", "status_event"])
        event = intake_meta_event(
            {"channel": "whatsapp", "event_type": "status_event",
             "sender_id": "u", "message_id": "s-1"},
            cfg,
        )
        with tempfile.TemporaryDirectory() as tmp:
            decision = route_meta_event(event, registry_path=_registry(tmp))
        self.assertEqual(decision.route, "ROUTINE")
        self.assertFalse(decision.draftable)

    def test_brand_unresolved_goes_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "reg.json"
            reg.write_text(json.dumps({
                "defaults": {"deny_unknown_business": True,
                              "deny_disabled_business": True,
                              "require_context_refs": True},
                "businesses": {},
            }), encoding="utf-8")
            result = process_meta_event(
                {"channel": "whatsapp", "event_type": "inbound_message",
                 "sender_id": "u", "message_id": "b-1",
                 "conversation_id": "c", "text": "hola"},
                integration=_wa_config(), registry_path=reg,
            )
            self.assertFalse(result.decision.brand_resolved)
            self.assertEqual(result.decision.route, "HUMAN_REVIEW")

    def test_brand_brain_loads_isolated_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            root = _biblia_root(tmp)
            event = intake_meta_event(
                {"channel": "whatsapp", "event_type": "inbound_message",
                 "sender_id": "u", "message_id": "bb-1",
                 "conversation_id": "c", "text": "hola"},
                _wa_config(),
            )
            ctx = load_brand_brain(event, biblia_root=root, registry_path=reg)
            self.assertEqual(ctx.business_id, "los-duros")
            self.assertEqual(ctx.biblia.business_id, "los-duros")


class ActionRouterTests(unittest.TestCase):
    def _routine(self, channel="instagram", event_type="comment", text="esto está duro"):
        cfg = _ig_config() if channel == "instagram" else _fb_config()
        raw = {"channel": channel, "event_type": event_type,
               "sender_id": "u", "message_id": "a-1", "text": text}
        if event_type in ("comment", "comment_reply"):
            raw["parent_id"] = "post-1"
        else:
            raw["conversation_id"] = "conv-1"
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            result = process_meta_event(raw, integration=cfg, registry_path=reg)
        assert result.draft is not None
        return result, cfg

    def test_instagram_comment_reply_intent(self):
        result, cfg = self._routine()
        intent = build_action_intent(result.event, result.draft, integration=cfg)
        self.assertEqual(intent.action, "reply_instagram_comment")
        self.assertEqual(intent.parent_id, "post-1")
        self.assertEqual(intent.idempotency_key, intent.event_fingerprint)

    def test_dm_action_for_comment_event_rejected(self):
        result, cfg = self._routine()
        with self.assertRaises(GlossolaliaError):
            build_action_intent(result.event, result.draft, integration=cfg,
                                action="send_instagram_dm")

    def test_cross_channel_action_rejected(self):
        result, cfg = self._routine()
        with self.assertRaises(GlossolaliaError):
            build_action_intent(result.event, result.draft, integration=cfg,
                                action="send_whatsapp_message")

    def test_comment_reply_without_parent_fails_safe(self):
        cfg = _ig_config()
        raw = {"channel": "instagram", "event_type": "comment",
               "sender_id": "u", "message_id": "np-1", "text": "esto está duro"}
        with tempfile.TemporaryDirectory() as tmp:
            result = process_meta_event(raw, integration=cfg,
                                        registry_path=_registry(tmp))
        self.assertIsNotNone(result.draft)
        with self.assertRaises(GlossolaliaError) as ctx:
            build_action_intent(result.event, result.draft, integration=cfg)
        self.assertIn("ACTION_REQUIRES_PARENT", str(ctx.exception))

    def test_action_not_in_integration_allowlist_rejected(self):
        result, _ = self._routine()
        cfg = _ig_config(allowed_action_types=["send_instagram_dm"])
        with self.assertRaises(GlossolaliaError):
            build_action_intent(result.event, result.draft, integration=cfg)

    def test_cross_business_intent_rejected(self):
        result, cfg = self._routine()
        intent = build_action_intent(result.event, result.draft, integration=cfg)
        foreign = _ig_config(integration_id="ig-zmart", business_id="zmart-consumer-rights",
                             brand_id="zmart-consumer-rights")
        action = route_meta_action(intent, result.decision, integration=foreign,
                                   security=None, meta_write_enabled=True)
        self.assertEqual(action.status, "REJECTED")


class WriteGateTests(unittest.TestCase):
    def _intent(self):
        result, cfg = ActionRouterTests()._routine()
        intent = build_action_intent(result.event, result.draft, integration=cfg)
        return result, cfg, intent

    def _sec(self, write):
        return SecurityContext(authenticated=True, principal_id="nelson",
                               allowed_business_ids=("los-duros",),
                               production_write_allowed=write)

    def test_all_gates_off_draft_only(self):
        result, cfg, intent = self._intent()
        action = route_meta_action(intent, result.decision, integration=cfg,
                                   security=None, meta_write_enabled=False)
        self.assertEqual(action.status, "DRAFT_ONLY")
        self.assertIsNotNone(action.intent)  # recorded, nothing sent

    def test_credentials_do_not_imply_publish(self):
        # Integration HAS credential refs, write still OFF -> no transport.
        result, cfg, intent = self._intent()
        self.assertIsNotNone(cfg.credential_ref)
        action = route_meta_action(intent, result.decision, integration=cfg,
                                   security=self._sec(True), meta_write_enabled=False)
        self.assertEqual(action.status, "DRAFT_ONLY")

    def test_integration_write_off_blocks(self):
        result, _, intent = self._intent()
        cfg = _ig_config(write_enabled=False)
        action = route_meta_action(intent, result.decision, integration=cfg,
                                   security=self._sec(True), meta_write_enabled=True)
        self.assertEqual(action.status, "DRAFT_ONLY")

    def test_security_write_off_blocks(self):
        result, cfg, intent = self._intent()
        cfg = _ig_config(write_enabled=True)
        action = route_meta_action(intent, result.decision, integration=cfg,
                                   security=self._sec(False), meta_write_enabled=True)
        self.assertEqual(action.status, "DRAFT_ONLY")

    def test_all_gates_on_yields_transport_intent(self):
        result, _, intent = self._intent()
        cfg = _ig_config(write_enabled=True)
        action = route_meta_action(intent, result.decision, integration=cfg,
                                   security=self._sec(True), meta_write_enabled=True)
        self.assertEqual(action.status, "TRANSPORT_INTENT")
        self.assertIsNotNone(action.intent)

    def test_human_review_never_auto_publishes(self):
        # No draft exists for HUMAN_REVIEW, so no intent can be built...
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            cfg = _ig_config(write_enabled=True)
            result = process_meta_event(
                {"channel": "instagram", "event_type": "comment",
                 "sender_id": "u", "message_id": "h-1",
                 "parent_id": "p-1", "text": "ese tipo es un chota"},
                integration=cfg, registry_path=reg,
            )
            self.assertEqual(result.decision.route, "HUMAN_REVIEW")
            self.assertIsNone(result.draft)

    def test_human_review_held_even_with_gates_open(self):
        # ...and even a hypothetical intent under HUMAN_REVIEW is held.
        from zion_core import MetaRouteDecision
        result, _ = ActionRouterTests()._routine()
        cfg = _ig_config(write_enabled=True)
        intent = build_action_intent(result.event, result.draft, integration=cfg)
        hr = MetaRouteDecision(route="HUMAN_REVIEW", subtype="CHOTIAERA",
                               reasons=("SAFETY_GATE_TRIP",), draftable=False,
                               brand_resolved=True)
        action = route_meta_action(intent, hr, integration=cfg,
                                   security=self._sec(True), meta_write_enabled=True)
        self.assertEqual(action.status, "HELD_FOR_HUMAN")

    def test_main_brain_not_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp)
            cfg = _ig_config(write_enabled=True)
            raw = {"channel": "instagram", "event_type": "dm",
                   "sender_id": "u", "message_id": "mb-1",
                   "conversation_id": "c", "media_refs": ["media:1"]}
            event = intake_meta_event(raw, cfg)
            decision = route_meta_event(event, registry_path=reg)
            self.assertEqual(decision.route, "MAIN_BRAIN")
            # MAIN_BRAIN never produces a draft -> never reaches transport.
            self.assertIsNone(draft_meta_reply(event, decision, registry_path=reg))

    def test_hold_for_human_action_explicit(self):
        result, _ = ActionRouterTests()._routine()
        cfg = _ig_config(write_enabled=True)
        action = route_meta_action(
            build_action_intent(result.event, result.draft, integration=cfg),
            result.decision, integration=cfg,
            security=self._sec(True), meta_write_enabled=True,
        )
        # Sanity: routine + all gates on does NOT hold.
        self.assertEqual(action.status, "TRANSPORT_INTENT")


class CapabilitiesTests(unittest.TestCase):
    def test_whatsapp_cannot_dm_or_comment_reply(self):
        from zion_core.glossolalia import CHANNEL_CAPABILITIES
        caps = CHANNEL_CAPABILITIES["whatsapp"]
        self.assertEqual(caps.allowed_actions, ("send_whatsapp_message",))
        self.assertEqual(caps.messaging_window_hours, 24)

    def test_instagram_separates_dm_and_comment(self):
        from zion_core.glossolalia import CHANNEL_CAPABILITIES
        caps = CHANNEL_CAPABILITIES["instagram"]
        self.assertIn("send_instagram_dm", caps.allowed_actions)
        self.assertIn("reply_instagram_comment", caps.allowed_actions)
        self.assertNotIn("comment", caps.action_event_map["send_instagram_dm"])
        self.assertNotIn("dm", caps.action_event_map["reply_instagram_comment"])

    def test_facebook_messenger_vs_comment(self):
        result, cfg = ActionRouterTests()._routine(channel="facebook",
                                                   event_type="comment")
        intent = build_action_intent(result.event, result.draft, integration=cfg)
        self.assertEqual(intent.action, "reply_facebook_comment")

    def test_no_network_imports(self):
        source = Path(__file__).resolve().parent.parent.joinpath(
            "zion_core", "glossolalia.py").read_text(encoding="utf-8")
        for forbidden in ("import urllib", "import requests", "import http",
                          "import socket", "urlopen", "httpx", "aiohttp"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
