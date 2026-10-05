# KTEMA / Property Appraiser / Orange Parcels_BCC — FREEZE RECORD

**STATUS: FROZEN / FUTURE WORK**

**Decision:** Nelson, 2026-10-04.
**Reason:** Property Appraiser is not currently required for Zero Lag WiFi.
It must not consume time or block active Zero Lag / ZION development.

**DO NOT CONTINUE PROPERTY APPRAISER WORK UNLESS NELSON REACTIVATES IT.**

This means: no Orange Parcels_BCC expansion, no new counties, no statewide
Florida property ingestion, no new property adapters, no additional scraping,
no additional property normalization — until Nelson explicitly reactivates.

This is a FREEZE, not a delete. All existing work below is preserved
as-is and must remain recoverable.

---

## Separation of concerns

```
ZERO LAG (zero-lag-wifi)
  ≠
PROPERTY APPRAISER / ORANGE PARCELS_BCC (KTEMA property intelligence)
```

- Zero Lag WiFi does NOT depend on Property Appraiser.
- Verified 2026-10-05: no Zero Lag module imports ktema
  (`antiphon.py`, `glossolalia.py`, `router.py`, `runtime.py`, `omar.py`,
  `biblia.py` — none import ktema; only `zion_core/__init__.py` re-exports
  ktema names).
- KTEMA is a standalone capability ("for consumption by authorized
  businesses", per `zmart360/MODULE_REGISTRY.md`); it is not wired into
  any Zero Lag flow.
- Do not create a dependency between the two systems.

---

## Preserved inventory (frozen at commit `75f425a`)

### Code
- `zion_core/ktema.py` (1512 lines) — FL property county-resolution
  adapter: `PropertyQuery` → `resolve_county()` against the embedded
  versioned ZIP→county table → `PropertySourceRouter` (never falls back to
  a neighboring county) → `fetch_intent()` (intent only, never fetches) →
  `normalize()` → validation gates → tenant-isolated `KtemaCache`.
  Deterministic and pure: no network, no geocoding, no LLM. Transport
  lives OUTSIDE ZION. `business_id` always re-validated via SAN PEDRO;
  unknown/disabled/spoofed IDs fail closed.
- `zion_core/ktema_orange.py` (224 lines) — `OrangeParcelsBccSource`
  (`source_id="orange-parcels-bcc"`): normalizes already-fetched ArcGIS
  JSON from the official Orange County Parcels_BCC layer into
  `PropertyProfile`. Schema verified 2026-10-04. Owner fields intentionally
  not consumed. NaN/±inf rejected as
  `KTEMA_ADAPTER_RESPONSE_MALFORMED:{field}-non-finite` (fail-closed,
  fixed 2026-10-05). NOT default-routed; only the fixture source is
  published by default.
- `zion_core/ktema_county_data.json` — 114-ZIP county table:
  Orange 38, Seminole 13, Volusia 30, Lake 24 single-county ZIPs;
  9 genuinely cross-county ZIPs (raise `KTEMA_COUNTY_AMBIGUOUS`, never
  guessed). `meta.built_from` lists the 4 official sources verbatim
  (Orange County Parcels_BCC FeatureServer layer 5 SITUS_ZIP;
  Seminole County PA daily CAMA CSV, vintage 2026-10-03;
  Volusia County GIS Address Situs FeatureServer layer 2;
  Lake County GIS Address Locations FeatureServer layer 11).
  `PARCEL_PATTERNS` ships EMPTY by design (parcel IDs → INCONCLUSIVE until
  patterns are verified against official PA sources).
- Exports in `zion_core/__init__.py` (`KtemaError`, `PropertyProfile`,
  `PropertySourceRegistry`, `KtemaCache`, `plan_ktema_batch`,
  `OrangeParcelsBccSource`, …).

### Tests (139, all passing at freeze)
- `tests/test_zion_ktema_county.py` (39) — county resolution, ambiguity,
  out-of-coverage.
- `tests/test_zion_ktema_profile.py` (29) — profile validation gates.
- `tests/test_zion_ktema_sources.py` (33) — source protocol/registry/router.
- `tests/test_zion_ktema_cache_isolation.py` (24) — tenant-isolated cache.
- `tests/test_zion_ktema_orange.py` (10) — Orange adapter normalization.
- `tests/test_zion_ktema_exports.py` (4) — public export surface.

### Docs and decisions
- `zmart360/MODULE_REGISTRY.md` → "KTEMA" section (responsibility,
  boundaries, MUST NOT list).
- `zmart360/BIBLIA/CHANGELOG.md` — KTEMA audit-fix entries.
- `.agents/ktema_adversarial_report.md` and
  `.agents/ktema_closure_adversarial_report.md` — adversarial findings;
  the P0 (cache owner gate bypass) was fixed before freeze
  (`KtemaCache.put` now fails closed with `KTEMA_OWNER_UNAUTHORIZED`
  unless `owner_authorized=True`).
- Architectural decisions (from module docstrings and registry):
  NOT_FOUND = "this source produced no match", never proof the property
  does not exist; multi-county ZIP raises instead of guessing;
  `FetchIntent.target_descriptor` is opaque (`fixture://…` or the source's
  own scheme — the module never builds URLs); cache is in-memory;
  negative (NOT_FOUND) entries require a configured validity (no eternal
  negatives).

### Discoveries
- 9 FL ZIPs verified genuinely cross-county on both sides from official
  sources (32102, 32703, 32720, 32751, 32757, 32776, 32789, 32792, 34787).
- Seminole extraction: 181,244 parcels; 16,461 had empty PrimaryAddress
  and contributed no ZIP (fail-closed, not guessed).
- ZIP 33935 (Hendry/Glades) documented as the canonical out-of-coverage
  multi-county example — intentionally NOT in the shipped table.

---

## Known limitations at freeze (evidence only, not a roadmap)

- `PARCEL_PATTERNS` empty → every `parcel_id` resolves INCONCLUSIVE; no
  parcel reaches a source until per-county patterns are verified.
- Cache is in-memory (no persistence yet).
- Only the fixture source is published by default; the Orange adapter
  exists and is schema-verified but not default-routed.
- Seminole, Volusia, Lake real adapters pending schema/endpoint
  verification (per MODULE_REGISTRY.md).
- Known weaknesses recorded in `.agents/ktema_closure_adversarial_report.md`
  (P1-1 SCAN-field smuggling not rejected in `validate_property_profile`;
  P1-4 `raw_reference` interpolates `source_record_id`; P1-5 no staleness
  marking on cached VERIFIED profiles; P2 items: `FetchIntent` direct
  construction bypasses the descriptor gate, batch `latitude="abc"`
  raises raw `ValueError`, parcel_id containing `"http"` trips the
  descriptor check, plus test gaps). None were judged blocking for a
  freeze; they are recorded for whoever reactivates.

## Where the work stopped

Last functional commit: `8e269c3 feat(ktema): add verified Orange Parcels_BCC
adapter`, followed by audit hardening (`0d634d7`, `75f425a` KTEMA items).
The last recorded recommendation (2026-10-04, before the freeze decision)
was: FL-DOR adapter + first real county adapter (Orange Parcels_BCC).
Since then the Orange adapter was implemented and schema-verified but not
default-routed — so the remaining step, whenever Nelson reactivates, is:
decide routing/publication of the Orange adapter, then FL-DOR and the
Seminole/Volusia/Lake adapters after schema/endpoint verification.
Nothing beyond this was specified; do not invent further scope.

---

**Checkpoint verified:** 139/139 KTEMA tests pass; full suite 649/649 PASS
at freeze commit. Working tree clean. No push, no deploy, no main changes.
