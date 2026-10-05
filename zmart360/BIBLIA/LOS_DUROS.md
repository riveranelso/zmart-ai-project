# LOS DUROS — Canonical Operating Knowledge

Status: canonical BIBLIA knowledge for the Los Duros brand.
Owner: Nelson.
Purpose: permanent brand rules for Los Duros automation, recorded verbatim
from owner approval. Brand voice, claims, assets, markets, compliance and
CTAs remain isolated to this brand unless an explicit global rule says
otherwise.

## YouTube comment CTA rotation
Permanent rule for YouTube comment replies (owner-approved 2026-10-04):

- Every YouTube comment reply MUST close with a contextual SUBSCRIBE + SHARE CTA.
- Never repeat the same CTA mechanically across comments: rotate the CTA and
  adapt it naturally to the comment's content and tone.
- Approved base variants (verbatim — do not alter):
  1. 🔔 Suscribete pa que no te pierdas lo proximo y compartelo con tu pana a ver que dice 😂
  2. 🔔 Suscribete pa que no te pierdas lo proximo y compartelo con ese pana que sabe la que hay.
  3. 🔔 Suscribete pa que no te pierdas lo proximo y compartelo con el pana que va a entender esa 😂
  4. 🔔 Suscribete pa que no te pierdas lo proximo y compartelo con tu pana pa que vea el revolu 😂
- ZION may compose new variants when the context warrants it, only if they:
  - sound natural and boricua;
  - relate to the comment;
  - carry SUBSCRIBE + SHARE intent;
  - invite interaction;
  - do not look like copy/paste;
  - respect every existing Los Duros rule, including NO CHOTIAERA, no street
    codes, no sensitive information, no automatic defense of Angel Doze or
    any artist, natural boricua tone (no forced slang, avoid "acho" and
    "mojate", use "tiraera" where appropriate), only KEY WORDS in uppercase,
    short copy.
- Enforcement is behavioral, not just documentation: `zion_core/antiphon.py`
  (`CTA_VARIANTS`, `validate_cta`, `compose_cta_variant`, verbatim CTA
  appended by `draft_reply`) and `tests/test_zion_antiphon.py`
  (`CTARotationTests`).
