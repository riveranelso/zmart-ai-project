"""Adversarial tests for ANTIPHON (zion_core.antiphon).

Covers: intake validation, SAN PEDRO brand resolution (fail closed),
classification routing, the safety/chotiaera gate, Los Duros draft rules,
the write gate, cross-business isolation, determinism, and the no-network
invariant.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zion_core import (
    AntiphonError,
    CTA_VARIANTS,
    HUMAN_REVIEW,
    MAIN_BRAIN,
    ROUTINE,
    classify_comment,
    compose_cta_variant,
    draft_reply,
    intake_comment,
    process_comment,
    publish_reply,
    resolve_brand,
    validate_cta,
)
from zion_core import antiphon as antiphon_module
from zion_core.gates import SecurityContext


OWNER_EXAMPLE = (
    "Esa parte fue la que puso a todo el mundo a debatir "
    "\U0001F602 ¿tu crees que RANDY tenia razon o INDIO lo puso en su sitio? "
    "Suscribete pa que no te pierdas la parte 2 y comparteselo a un pana que se enfogone."
)


def _registry(tmp, businesses):
    path = Path(tmp) / "registry.json"
    path.write_text(json.dumps({
        "defaults": {
            "deny_unknown_business": True,
            "deny_disabled_business": True,
            "require_context_refs": True,
        },
        "businesses": businesses,
    }), encoding="utf-8")
    return path


def _los_duros_registry(tmp, isolation_key="los-duros", enabled=True):
    return _registry(tmp, {
        "los-duros": {
            "enabled": enabled,
            "isolation_key": isolation_key,
            "context_refs": ["zmart360/BIBLIA/GLOBAL.md"],
        }
    })


def _comment(text, **overrides):
    payload = {
        "comment_id": "cmt-1",
        "video_id": "vid-1",
        "author": "fan123",
        "text": text,
    }
    payload.update(overrides)
    return intake_comment(payload)


class IntakeTests(unittest.TestCase):
    def test_valid_payload_normalizes(self):
        c = _comment("esto está duro")
        self.assertEqual(c.comment_id, "cmt-1")
        self.assertEqual(c.business_id, "los-duros")  # default scope
        self.assertEqual(c.like_count, 0)
        self.assertFalse(c.truncated)

    def test_missing_comment_id_rejected(self):
        with self.assertRaises(AntiphonError):
            intake_comment({"video_id": "v", "author": "a", "text": "hola"})

    def test_empty_text_rejected(self):
        with self.assertRaises(AntiphonError):
            _comment("   ")

    def test_non_dict_payload_rejected(self):
        with self.assertRaises(AntiphonError):
            intake_comment("not a dict")

    def test_negative_like_count_rejected(self):
        with self.assertRaises(AntiphonError):
            _comment("hola", like_count=-1)

    def test_bool_like_count_rejected(self):
        with self.assertRaises(AntiphonError):
            _comment("hola", like_count=True)

    def test_overlong_text_truncated_and_flagged(self):
        c = _comment("x" * 6000)
        self.assertTrue(c.truncated)
        self.assertEqual(len(c.text), 5000)


class BrandResolutionTests(unittest.TestCase):
    def test_los_duros_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            brand = resolve_brand(_comment("hola"), reg)
            self.assertTrue(brand.resolved)
            self.assertEqual(brand.isolation_key, "los-duros")

    def test_other_business_fails_closed(self):
        # Even a real, enabled business never gets a Los Duros draft path.
        with tempfile.TemporaryDirectory() as tmp:
            reg = _registry(tmp, {
                "los-duros": {"enabled": True, "isolation_key": "los-duros",
                              "context_refs": ["zmart360/BIBLIA/GLOBAL.md"]},
                "zmart-consumer-rights": {"enabled": True, "isolation_key": "zmart-consumer-rights",
                                          "context_refs": ["zmart360/BIBLIA/GLOBAL.md"]},
            })
            comment = _comment("esto está duro", business_id="zmart-consumer-rights")
            brand = resolve_brand(comment, reg)
            self.assertFalse(brand.resolved)
            self.assertEqual(brand.reason, "CROSS_BUSINESS_COMMENT")

    def test_unknown_business_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            comment = _comment("hola", business_id="nope-business")
            brand = resolve_brand(comment, reg)
            self.assertFalse(brand.resolved)

    def test_isolation_key_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp, isolation_key="tampered-key")
            brand = resolve_brand(_comment("hola"), reg)
            self.assertFalse(brand.resolved)
            self.assertEqual(brand.reason, "ISOLATION_KEY_MISMATCH")

    def test_disabled_business_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp, enabled=False)
            brand = resolve_brand(_comment("hola"), reg)
            self.assertFalse(brand.resolved)


class ClassificationTests(unittest.TestCase):
    def _route(self, text, **kw):
        return classify_comment(_comment(text, **kw))

    def test_opinion_is_routine(self):
        c = self._route("esto está duro, me encanta")
        self.assertEqual((c.route, c.subtype), (ROUTINE, "opinion"))

    def test_disagreement_is_routine(self):
        c = self._route("no estoy de acuerdo con eso")
        self.assertEqual(c.route, ROUTINE)

    def test_artist_support_is_routine(self):
        c = self._route("Anuel es el mejor, mi gallo")
        self.assertEqual(c.route, ROUTINE)

    def test_artist_comparison_is_routine(self):
        c = self._route("Anuel vs Bad Bunny, Anuel le gana")
        self.assertEqual(c.route, ROUTINE)

    def test_entertainment_is_routine(self):
        c = self._route("jajajaja qué risa")
        self.assertEqual(c.route, ROUTINE)

    def test_simple_question_is_routine(self):
        c = self._route("¿cuándo sale la parte 2?")
        self.assertEqual(c.route, ROUTINE)

    def test_chotiaera_goes_human_review(self):
        c = self._route("ese tipo es un chota, lo sapeó todo")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "CHOTIAERA"))

    def test_threat_goes_human_review(self):
        c = self._route("te voy a matar cuando te vea")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "THREAT_VIOLENCE"))

    def test_doxxing_goes_human_review(self):
        c = self._route("su número es 787-555-0134 llámalo")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "DOXXING_PRIVACY"))

    def test_serious_accusation_goes_human_review(self):
        c = self._route("ese es un asesino, todo el mundo lo sabe")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "SERIOUS_ACCUSATION"))

    def test_sensitive_request_goes_human_review(self):
        c = self._route("dónde vive, pasa el contacto")
        self.assertEqual(c.route, HUMAN_REVIEW)

    def test_safety_beats_routine_match(self):
        # Entertainment markers do not save a chotiaera comment.
        c = self._route("jajaja ese chota habló de más")
        self.assertEqual(c.route, HUMAN_REVIEW)

    def test_irony_goes_main_brain(self):
        c = self._route('claro que sí, tremendo cantante jaj "qué voz"')
        self.assertEqual(c.route, MAIN_BRAIN)

    def test_too_short_goes_main_brain(self):
        c = self._route("ok")
        self.assertEqual((c.route, c.subtype), (MAIN_BRAIN, "ambiguous"))

    def test_no_routine_match_goes_main_brain(self):
        c = self._route("el cielo está azul hoy en la tarde")
        self.assertEqual((c.route, c.subtype), (MAIN_BRAIN, "ambiguous"))

    def test_truncated_goes_main_brain(self):
        c = self._route("x" * 6000 + " me encanta")
        self.assertEqual((c.route, c.subtype), (MAIN_BRAIN, "insufficient_context"))


class DraftTests(unittest.TestCase):
    def _routine(self, text, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            comment = _comment(text, **kw)
            brand = resolve_brand(comment, reg)
            classification = classify_comment(comment)
            self.assertEqual(classification.route, ROUTINE)
            return draft_reply(comment, classification, brand=brand)

    def test_draft_has_cta_from_pool(self):
        draft = self._routine("esto está duro, me encanta")
        self.assertIn(draft.cta_variant, CTA_VARIANTS)
        self.assertIn(draft.cta_variant, draft.text)

    def test_draft_is_short(self):
        draft = self._routine("Anuel es el mejor, mi gallo")
        self.assertLessEqual(len(draft.text), 280)

    def test_draft_max_one_emoji(self):
        import re
        emoji_re = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
        for text in ("esto está duro", "jajajaja qué risa", "Anuel vs Bad Bunny"):
            draft = self._routine(text)
            # Owner-approved CTA variants are appended verbatim (they carry
            # up to 2 emojis: bell + laugh); the single-emoji rule applies
            # to the reply body, and the CTA must close the reply intact.
            self.assertIn(draft.cta_variant, CTA_VARIANTS)
            self.assertTrue(draft.text.endswith(draft.cta_variant))
            body = draft.text[: -len(draft.cta_variant)]
            self.assertLessEqual(len(emoji_re.findall(body)), 1)

    def test_draft_no_banned_words(self):
        for text in ("esto está duro me encanta", "no estoy de acuerdo",
                     "mi gallo es el mejor", "jajajaja qué risa",
                     "¿cuándo sale la parte 2?"):
            draft = self._routine(text)
            lowered = draft.text.lower()
            self.assertNotIn("acho", lowered)
            self.assertNotIn("mojate", lowered)
            self.assertNotIn("mójate", lowered)

    def test_draft_not_all_caps(self):
        draft = self._routine("esto está duro, me encanta")
        words = [w.strip(".,!?¿¡") for w in draft.text.split()]
        alpha = [w for w in words if w.isalpha() and len(w) > 2]
        upper = [w for w in alpha if w.isupper()]
        self.assertLess(len(upper) / len(alpha), 0.5)

    def test_draft_uses_artist_keyword_caps(self):
        # Frames with the {artist} slot render it as a KEYWORD in CAPS.
        seen = False
        for i in range(10):
            draft = self._routine("esto está duro", video_artist="randy",
                                  comment_id=f"art-{i}")
            if "RANDY" in draft.text:
                seen = True
                break
        self.assertTrue(seen, "expected an artist-slot frame with RANDY in caps")

    def test_draft_is_deterministic(self):
        a = self._routine("esto está duro, me encanta", comment_id="same-1")
        b = self._routine("esto está duro, me encanta", comment_id="same-1")
        self.assertEqual(a.text, b.text)

    def test_cta_rotates_across_comments(self):
        seen = set()
        for i in range(20):
            draft = self._routine("esto está duro", comment_id=f"rot-{i}")
            seen.add(draft.cta_variant)
        self.assertGreater(len(seen), 1)

    def test_owner_example_never_returned_verbatim(self):
        for i in range(30):
            draft = self._routine("esto está duro me encanta", comment_id=f"ex-{i}")
            self.assertNotEqual(draft.text, OWNER_EXAMPLE)

    def test_brand_addressed_detected(self):
        draft = self._routine("los duros, su canal está duro")
        self.assertTrue(draft.brand_addressed)

    def test_non_routine_never_drafted(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            comment = _comment("ese es un chota")
            brand = resolve_brand(comment, reg)
            classification = classify_comment(comment)
            self.assertEqual(classification.route, HUMAN_REVIEW)
            with self.assertRaises(AntiphonError):
                draft_reply(comment, classification, brand=brand)

    def test_cross_business_never_drafted(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            comment = _comment("esto está duro", business_id="zmart-consumer-rights")
            brand = resolve_brand(comment, reg)
            classification = classify_comment(comment)
            with self.assertRaises(AntiphonError):
                draft_reply(comment, classification, brand=brand)


class CTARotationTests(unittest.TestCase):
    """Pin the permanent YOUTUBE COMMENT CTA ROTATION brand rule."""

    def test_cta_pool_matches_approved_variants(self):
        self.assertEqual(
            CTA_VARIANTS,
            (
                "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con tu pana a ver que dice 😂",
                "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con ese pana que sabe la que hay.",
                "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con el pana que va a entender esa 😂",
                "🔔 Suscribete pa que no te pierdas lo proximo y compartelo con tu pana pa que vea el revolu 😂",
            ),
        )

    def test_cta_pool_carries_subscribe_plus_share(self):
        for variant in CTA_VARIANTS:
            lowered = variant.lower()
            self.assertIn("suscrib", lowered, variant)
            self.assertTrue(
                any(m in lowered for m in ("compart", "mandaselo", "pasalo")),
                variant,
            )

    def test_cta_pool_passes_policy(self):
        for variant in CTA_VARIANTS:
            self.assertEqual(validate_cta(variant), (), variant)

    def test_validate_cta_rejects_missing_intent(self):
        self.assertIn(
            "CTA_MISSING_SHARE_INTENT",
            validate_cta("Suscribete pa que no te pierdas lo proximo."),
        )
        self.assertIn(
            "CTA_MISSING_SUBSCRIBE_INTENT",
            validate_cta("Comparte esto con un pana que se enfogone."),
        )

    def test_validate_cta_rejects_banned_word_caps_and_accents(self):
        self.assertTrue(
            any(v.startswith("CTA_BANNED_WORD") for v in validate_cta(
                "🔔 Suscribete acho y compartelo con tu pana.")),
        )
        self.assertIn(
            "CTA_ALL_CAPS",
            validate_cta("🔔 SUSCRIBETE Y COMPARTELO CON TU PANA"),
        )
        self.assertIn(
            "CTA_ACCENTED_CHARS",
            validate_cta("🔔 Suscríbete y compártelo con tu pana."),
        )
        self.assertIn(
            "CTA_TOO_MANY_EMOJIS",
            validate_cta("🔔😂🤣 Suscribete y compartelo con tu pana."),
        )

    def test_compose_cta_variant_is_policy_clean(self):
        cta = compose_cta_variant("entienda la tiraera")
        self.assertEqual(validate_cta(cta), ())
        self.assertIn("entienda la tiraera", cta)
        self.assertIn("suscrib", cta.lower())

    def test_compose_cta_variant_strips_accents(self):
        cta = compose_cta_variant("vea el revolú")
        self.assertNotRegex(cta, "[áéíóúñü]")
        self.assertEqual(validate_cta(cta), ())

    def test_compose_cta_variant_rejects_banned_phrase(self):
        with self.assertRaises(AntiphonError):
            compose_cta_variant("acho que se moje")

    def test_compose_cta_variant_rejects_empty_phrase(self):
        with self.assertRaises(AntiphonError):
            compose_cta_variant("   ")

    def test_cta_pick_adapts_to_subtype_and_stays_deterministic(self):
        pick = antiphon_module._pick_cta
        self.assertEqual(pick("c-1", "opinion"), pick("c-1", "opinion"))
        seen = {
            pick(f"c-{i}", subtype)
            for i in range(12)
            for subtype in ("opinion", "disagreement", "artist_support")
        }
        self.assertGreater(len(seen), 1)

    def test_draft_rejects_policy_violating_cta(self):
        # Runtime guard: a tampered pool can never produce a draft.
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            comment = _comment("esto está duro", comment_id="tamper-1")
            brand = resolve_brand(comment, reg)
            classification = classify_comment(comment)
            self.assertEqual(classification.route, ROUTINE)
            with mock.patch.object(
                antiphon_module, "CTA_VARIANTS", ("Suscribete ya.",)
            ):
                with self.assertRaises(AntiphonError) as ctx:
                    draft_reply(comment, classification, brand=brand)
            self.assertIn("CTA_POLICY_VIOLATION", str(ctx.exception))


class WriteGateTests(unittest.TestCase):
    def _draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            comment = _comment("esto está duro", comment_id="pub-1")
            brand = resolve_brand(comment, reg)
            classification = classify_comment(comment)
            draft = draft_reply(comment, classification, brand=brand)
            return draft, comment

    def test_no_security_context_blocks_publish(self):
        draft, comment = self._draft()
        result = publish_reply(draft, comment, security=None)
        self.assertFalse(result.published)
        self.assertEqual(result.reason, "WRITE_GATE_DISABLED")
        self.assertIsNone(result.intent)

    def test_write_gate_false_blocks_publish(self):
        draft, comment = self._draft()
        sec = SecurityContext(authenticated=True, principal_id="nelson",
                              allowed_business_ids=("los-duros",),
                              production_write_allowed=False)
        result = publish_reply(draft, comment, security=sec)
        self.assertFalse(result.published)
        self.assertEqual(result.reason, "WRITE_GATE_DISABLED")
        self.assertIsNone(result.intent)

    def test_write_gate_enabled_yields_intent_not_network(self):
        draft, comment = self._draft()
        sec = SecurityContext(authenticated=True, principal_id="nelson",
                              allowed_business_ids=("los-duros",),
                              production_write_allowed=True)
        result = publish_reply(draft, comment, security=sec)
        # Intent ready for an external publisher; ANTIPHON never publishes.
        self.assertFalse(result.published)
        self.assertEqual(result.reason, "PUBLISH_INTENT_READY")
        self.assertIsNotNone(result.intent)
        self.assertEqual(result.intent.comment_id, "pub-1")
        self.assertEqual(result.intent.business_id, "los-duros")
        self.assertEqual(result.intent.text, draft.text)

    def test_draft_comment_mismatch_denied(self):
        draft, comment = self._draft()
        other = _comment("otro texto", comment_id="other-9")
        sec = SecurityContext(authenticated=True, principal_id="nelson",
                              allowed_business_ids=("los-duros",),
                              production_write_allowed=True)
        result = publish_reply(draft, other, security=sec)
        self.assertFalse(result.published)
        self.assertEqual(result.reason, "DRAFT_COMMENT_MISMATCH")

    def test_cross_business_publish_denied(self):
        draft, comment = self._draft()
        tampered = intake_comment({
            "comment_id": "pub-1", "video_id": "vid-1", "author": "x",
            "text": "esto está duro", "business_id": "zero-lag-wifi",
        })
        sec = SecurityContext(authenticated=True, principal_id="nelson",
                              allowed_business_ids=("los-duros", "zero-lag-wifi"),
                              production_write_allowed=True)
        result = publish_reply(draft, tampered, security=sec)
        self.assertFalse(result.published)
        self.assertEqual(result.reason, "CROSS_BUSINESS_PUBLISH_DENIED")


class PipelineTests(unittest.TestCase):
    def test_routine_end_to_end_no_publish_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            result = process_comment(
                {"comment_id": "e2e-1", "video_id": "v", "author": "a",
                 "text": "esto está duro, me encanta"},
                registry_path=reg,
            )
            self.assertEqual(result.classification.route, ROUTINE)
            self.assertIsNotNone(result.draft)
            self.assertIsNone(result.publish)

    def test_human_review_produces_no_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            result = process_comment(
                {"comment_id": "e2e-2", "video_id": "v", "author": "a",
                 "text": "ese tipo es un chota"},
                registry_path=reg,
            )
            self.assertEqual(result.classification.route, HUMAN_REVIEW)
            self.assertIsNone(result.draft)

    def test_cross_business_payload_goes_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            result = process_comment(
                {"comment_id": "e2e-3", "video_id": "v", "author": "a",
                 "text": "esto está duro", "business_id": "scan-water-intelligence"},
                registry_path=reg,
            )
            self.assertFalse(result.brand.resolved)
            self.assertEqual(result.classification.route, HUMAN_REVIEW)
            self.assertIsNone(result.draft)

    def test_attempt_publish_respects_write_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            sec = SecurityContext(authenticated=True, principal_id="nelson",
                                  allowed_business_ids=("los-duros",),
                                  production_write_allowed=False)
            result = process_comment(
                {"comment_id": "e2e-4", "video_id": "v", "author": "a",
                 "text": "esto está duro"},
                registry_path=reg, security=sec, attempt_publish=True,
            )
            self.assertIsNotNone(result.publish)
            self.assertEqual(result.publish.reason, "WRITE_GATE_DISABLED")


class SensitiveCaseTests(unittest.TestCase):
    """HUMAN_REVIEW #6 -- casos sensibles: menores, procesos legales."""

    def _route(self, text):
        return classify_comment(_comment(text))

    def test_minor_de_edad_goes_human_review(self):
        c = self._route("el chamaquito canta bien pero es menor de edad")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "SENSITIVE_CASE"))

    def test_nino_goes_human_review(self):
        c = self._route("ese niño tiene talento, cuídenlo")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "SENSITIVE_CASE"))

    def test_arresto_goes_human_review(self):
        c = self._route("lo arrestaron ayer, qué fuerte")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "SENSITIVE_CASE"))

    def test_juicio_goes_human_review(self):
        c = self._route("hay juicio pendiente con la disquera")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "SENSITIVE_CASE"))

    def test_sentencia_goes_human_review(self):
        c = self._route("la sentencia sale la semana que viene")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "SENSITIVE_CASE"))

    def test_menor_without_de_edad_does_not_trip(self):
        # "menor" alone (youngest sibling/friend) is not a sensitive case.
        c = self._route("el menor de mis panas la rompe, esto está duro")
        self.assertEqual(c.route, ROUTINE)

    def test_corte_haircut_does_not_trip(self):
        # Bare "corte" (haircut) is not the court; "la corte" would be.
        c = self._route("me hice un corte, esto está duro")
        self.assertEqual(c.route, ROUTINE)


class BrandRuleConflictTests(unittest.TestCase):
    """HUMAN_REVIEW #7 -- conflicto no resoluble deterministicamente."""

    def _route(self, text):
        return classify_comment(_comment(text))

    def test_opposing_valence_goes_human_review(self):
        c = self._route("Anuel es el mejor pero no estoy de acuerdo con lo que hizo")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "brand_rule_conflict"))

    def test_claim_hedge_goes_human_review(self):
        c = self._route("dicen que firmó con otra disquera")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "unverifiable_claim"))

    def test_supuestamente_goes_human_review(self):
        c = self._route("supuestamente viene pa PR el mes que viene")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "unverifiable_claim"))

    def test_caution_overlap_goes_human_review(self):
        c = self._route("esto está duro, ojalá la policía no lo pare en el camino")
        self.assertEqual((c.route, c.subtype), (HUMAN_REVIEW, "brand_rule_conflict"))

    def test_clean_routine_is_not_escalated(self):
        # Deterministic brand rule -> ROUTINE, never HUMAN_REVIEW.
        c = self._route("esto está duro, me encanta")
        self.assertEqual(c.route, ROUTINE)

    def test_clean_question_is_not_escalated(self):
        c = self._route("¿cuándo sale la parte 2?")
        self.assertEqual(c.route, ROUTINE)

    def test_deterministic_irony_stays_main_brain(self):
        # Irony has a clear deterministic rule -> MAIN_BRAIN, not human.
        c = self._route('claro que sí, tremendo cantante jaj "qué voz"')
        self.assertEqual((c.route, c.subtype), (MAIN_BRAIN, "irony"))

    def test_conflict_never_produces_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            comment = _comment("dicen que firmó con otra disquera")
            brand = resolve_brand(comment, reg)
            classification = classify_comment(comment)
            self.assertEqual(classification.route, HUMAN_REVIEW)
            with self.assertRaises(AntiphonError):
                draft_reply(comment, classification, brand=brand)


class AdversarialTests(unittest.TestCase):
    def test_module_imports_no_network_libraries(self):
        source = Path(__file__).resolve().parent.parent.joinpath(
            "zion_core", "antiphon.py").read_text(encoding="utf-8")
        for forbidden in ("import urllib", "import requests", "import http",
                          "import socket", "urlopen", "httpx", "aiohttp"):
            self.assertNotIn(forbidden, source)

    def test_draft_battery_never_breaks_brand_rules(self):
        import re
        emoji_re = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
        battery = [
            "esto está duro me encanta", "no estoy de acuerdo con eso",
            "Anuel es el mejor mi gallo", "Anuel vs Bad Bunny",
            "jajajaja qué risa", "¿cuándo sale la parte 2?",
            "los duros su canal está duro", "ese tema me fascina demasiado",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            reg = _los_duros_registry(tmp)
            for i, text in enumerate(battery):
                comment = _comment(text, comment_id=f"bat-{i}", video_artist="indio")
                brand = resolve_brand(comment, reg)
                classification = classify_comment(comment)
                if classification.route != ROUTINE:
                    continue
                draft = draft_reply(comment, classification, brand=brand)
                lowered = draft.text.lower()
                self.assertNotIn("acho", lowered, text)
                self.assertNotIn("mojate", lowered, text)
                # CTA appended verbatim (up to 2 emojis); single-emoji rule
                # applies to the body.
                self.assertTrue(draft.text.endswith(draft.cta_variant), text)
                body = draft.text[: -len(draft.cta_variant)]
                self.assertLessEqual(len(emoji_re.findall(body)), 1, text)
                self.assertLessEqual(len(draft.text), 280, text)
                self.assertIn(draft.cta_variant, CTA_VARIANTS, text)
                self.assertNotEqual(draft.text, OWNER_EXAMPLE, text)

    def test_safety_battery_all_human_review(self):
        battery = [
            "el chota del barrio habló",
            "te voy a matar",
            "llámalo al 787-555-0100",
            "dónde vive ese tipo",
            "es un violador",
            "sapo, delataste a todo el mundo",
        ]
        for text in battery:
            c = classify_comment(_comment(text))
            self.assertEqual(c.route, HUMAN_REVIEW, text)


if __name__ == "__main__":
    unittest.main()
