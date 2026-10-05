"""Invariant tests: no automatic artist defense in any draft frame pool.

Canonical: LOS_DUROS.md "Comment replies" (never automatically defend
Angel Doze or any artist) and "Response psychology" (respond to the
argument, never gratuitously attack the person). The frame pools are the
structural enforcement: no defense templates exist, and no frame takes an
artist's side by reflex.
"""
import re
import unicodedata

from zion_core import antiphon


def _norm(text):
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()


# First-person defense phrasing: taking the artist's side by reflex.
_DEFENSE_MARKERS = (
    r"\bdefiendo\b",
    r"\bno\s+es\s+culpa\s+de\b",
    r"\bdejen\s+de\s+atacar\b",
    r"\bpobre\b",
    r"\bestan\s+siendo\s+injustos\b",
)

# Person-directed attacks: never in any frame.
_ATTACK_MARKERS = (
    r"\bestupido\b",
    r"\bbruto\b",
    r"\bignorante\b",
    r"\bidiota\b",
    r"\bimbecil\b",
)


def _all_frames():
    pools = [antiphon._FRAMES, antiphon._ELEVATED_FRAMES]
    for pool in pools:
        for pairs in pool.values():
            for connect, question in pairs:
                yield connect, question
    for connect, question in antiphon._FALLBACK_FRAMES:
        yield connect, question


def test_no_frame_defends_any_artist():
    for connect, question in _all_frames():
        text = _norm(f"{connect} {question}")
        for marker in _DEFENSE_MARKERS:
            assert not re.search(marker, text), f"defense marker {marker} in frame"


def test_no_frame_attacks_the_person():
    for connect, question in _all_frames():
        text = _norm(f"{connect} {question}")
        for marker in _ATTACK_MARKERS:
            assert not re.search(marker, text), f"attack marker {marker} in frame"


def test_no_frame_confirms_unverified_claims():
    # Frames never present rumor as fact.
    rumor_markers = (r"\bdicen\s+que\b", r"\bsupuestamente\b", r"\bes\s+un\s+hecho\b")
    for connect, question in _all_frames():
        text = _norm(f"{connect} {question}")
        for marker in rumor_markers:
            assert not re.search(marker, text), f"rumor marker {marker} in frame"
