"""Wiring tests: debate level inside antiphon classify/draft.

Canonical: LOS_DUROS.md "Response psychology".
"""
import re
import unicodedata

import pytest

from zion_core import antiphon, debate


def _norm(text):
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()


def _comment(text, cid="c-debate-1"):
    return antiphon.intake_comment({
        "comment_id": cid, "video_id": "v1", "author": "fan1", "text": text,
    })


def _brand():
    return antiphon.BrandResolution(
        business_id="los-duros", isolation_key="los-duros",
        context_refs=(), resolved=True, reason="BRAND_RESOLVED",
    )


def test_elevated_comment_classifies_with_level():
    classification = antiphon.classify_comment(_comment(
        "No estoy de acuerdo porque en el 2019 los numeros, de hecho, "
        "contradicen esa version de los hechos"
    ))
    assert classification.debate_level == debate.ELEVATED


def test_standard_comment_stays_standard():
    classification = antiphon.classify_comment(_comment("Anuel es el mejor"))
    assert classification.route == antiphon.ROUTINE
    assert classification.debate_level == debate.STANDARD


def test_elevated_draft_uses_elevated_pool():
    comment = _comment(
        "No estoy de acuerdo porque en el 2019 los numeros, de hecho, "
        "contradicen esa version de los hechos",
        cid="c-debate-elev",
    )
    classification = antiphon.classify_comment(comment)
    assert classification.route == antiphon.ROUTINE
    assert classification.debate_level == debate.ELEVATED
    draft = antiphon.draft_reply(comment, classification, brand=_brand())
    elevated_texts = [
        t for pool in antiphon._ELEVATED_FRAMES.values() for pair in pool for t in pair
    ]
    assert any(t in draft.text for t in elevated_texts)


def test_standard_draft_uses_standard_pool():
    comment = _comment("Anuel es el mejor", cid="c-debate-std")
    classification = antiphon.classify_comment(comment)
    draft = antiphon.draft_reply(comment, classification, brand=_brand())
    elevated_texts = [
        t for pool in antiphon._ELEVATED_FRAMES.values() for pair in pool for t in pair
    ]
    assert not any(t in draft.text for t in elevated_texts)


def test_elevated_frames_never_attack_the_person():
    for pool in antiphon._ELEVATED_FRAMES.values():
        for connect, question in pool:
            normalized = _norm(f"{connect} {question}")
            for word in antiphon._PERSON_ATTACK_WORDS:
                assert not re.search(rf"\b{re.escape(word)}\b", normalized), (
                    f"person-attack word {word!r} in elevated frame"
                )


def test_elevated_draft_keeps_brand_gates():
    comment = _comment(
        "Anuel le gana a Bad Bunny porque los datos de los ultimos anos, "
        "de hecho, lo confirman",
        cid="c-debate-gate",
    )
    classification = antiphon.classify_comment(comment)
    assert classification.route == antiphon.ROUTINE
    draft = antiphon.draft_reply(comment, classification, brand=_brand())
    assert draft.cta_variant in antiphon.CTA_VARIANTS
    assert antiphon.validate_cta(draft.cta_variant) == ()


def test_deterministic_elevated_selection():
    text = "No estoy de acuerdo porque la evidencia contradice eso, sin embargo hay matices"
    kwargs = dict(cid="c-debate-det")
    c1 = antiphon.draft_reply(
        _comment(text, **kwargs),
        antiphon.classify_comment(_comment(text, **kwargs)),
        brand=_brand(),
    )
    c2 = antiphon.draft_reply(
        _comment(text, **kwargs),
        antiphon.classify_comment(_comment(text, **kwargs)),
        brand=_brand(),
    )
    assert c1.text == c2.text
