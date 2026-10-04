# ZION CORE — Module Registry

Canonical discovery source for agents. This document is the human-readable
mirror of `zion_core/paradosis.py` (`MODULE_REGISTRY`); the code is the
authority when they differ. Responsibilities are derived from the real
modules and tests — never invented.

Principle: **ZION is the system. Agents work ON ZION. Agents are not ZION.**

Before any mission, an agent receives a `MissionPacket` (see
`zion_core/paradosis.py`) that names only the relevant modules below plus
their `context_refs`. Agents never load the whole repo when a subset
suffices.

## OMAR — `zion_core/omar.py`

**Responsibility:** Stable application entrypoints: prepare missions with
isolated canonical knowledge, dispatch them, materialize execution contexts,
close ANGEL work through the learning loop.
**Inputs:** mission dict, business_id, biblia_root.
**Outputs:** MissionContext, OmarMissionDispatch, AngelExecutionContext.
**Dependencies:** biblia, registry, router, apokrisis.
**Boundaries:** business isolation via SAN PEDRO; no production infra selection.
**MUST NOT:** invent canonical knowledge; bypass gates; dispatch without EXAPOSTELLO.
**Context:** `zmart360/OMAR.md`.

## SAN PEDRO — `zion_core/registry.py`

**Responsibility:** Key/registry resolution — the authority for tenant
identity. Resolves business_id → canonical BusinessContext (isolation_key,
context_refs).
**Inputs:** business_id. **Outputs:** BusinessContext.
**Dependencies:** none.
**Boundaries:** deny_unknown_business, deny_disabled_business, require_context_refs.
**MUST NOT:** invent businesses; override isolation keys; serve disabled tenants.
**Context:** `zmart360/SAN_PEDRO.md`, `zmart360/san_pedro_registry.json`.

## SAN GABRIEL / EXAPOSTELLO — `zion_core/router.py`

**Responsibility:** Mission routing and dispatch: validate the MEGILLAH
mission, resolve the DEREKH route, evaluate the four fail-closed gates,
allocate ANGELS via DIATASSO.
**Inputs:** mission dict, derekh routes, registry, security context.
**Outputs:** DispatchDecision (DISPATCH | REQUIRE_HUMAN_REVIEW).
**Dependencies:** registry, gates, allocator, cronicas.
**Boundaries:** deny_unregistered_route; least_privilege; all four gates must pass.
**MUST NOT:** dispatch on gate denial; invent routes; call external endpoints.
**Context:** `zmart360/SAN_GABRIEL.md`, `zmart360/derekh.yaml`, `zmart360/GATES.md`.

## GATES — `zion_core/gates.py`

**Responsibility:** Fail-closed admission gates: SERAPHIM (integrity),
CHERUBIM (security/boundaries), THRONES (policy/authority), POWERS
(runtime enforcement). Carries SecurityContext.
**Inputs:** mission dict, isolation_key, context_refs, SecurityContext.
**Outputs:** GateResult per gate.
**Dependencies:** none.
**Boundaries:** a single denial blocks dispatch; no external effects.
**MUST NOT:** execute actions; replace downstream auth/policy engines; allow on ambiguity.
**Context:** `zmart360/GATES.md`, `zmart360/CHERUBIM.md`.

## DIATASSO — `zion_core/allocator.py`

**Responsibility:** Deterministic bounded appointment of ANGELS to a mission
under the resolved COMMAND/HOST.
**Inputs:** mission, command, host, business context.
**Outputs:** DiatassoCommission / AngelAssignment.
**Dependencies:** none.
**Boundaries:** bounded angel count; least privilege.
**MUST NOT:** dispatch (EXAPOSTELLO sends); exceed bounds; cross tenants.
**Context:** `zmart360/ANGELS.md`.

## APOKRISIS — `zion_core/apokrisis.py`

**Responsibility:** Structured ANGEL response after bounded work; close
missions and feed the learning loop. Reports status and references; grants
no authority.
**Inputs:** angel_id, mission_id, status, business_id.
**Outputs:** Apokrisis, learning cycle result.
**Dependencies:** holy_ghost, cronicas.
**Boundaries:** response only — never dispatches.
**MUST NOT:** dispatch missions; grant authority; mutate BIBLIA directly.
**Context:** `zmart360/HOLY_GHOST.md`.

## BIBLIA — `zion_core/biblia.py`

**Responsibility:** Canonical current knowledge retrieval, scoped per
business from the SAN PEDRO registry. CRONICAS history is never treated as
BIBLIA authority.
**Inputs:** business_id, biblia_root, registry_path.
**Outputs:** BibliaContext.
**Dependencies:** registry.
**Boundaries:** business-scoped retrieval; refs must stay inside root.
**MUST NOT:** cross business sections; treat history as canon; invent knowledge.
**Context:** `zmart360/BIBLIA/`.

## HOLY GHOST — `zion_core/holy_ghost.py`

**Responsibility:** Guidance and adaptive learning: derive learning signals
from completed ANGEL work, evaluate them, propose BIBLIA promotions.
Decides whether learning merits promotion.
**Inputs:** Apokrisis, correction signals, LearningIntent.
**Outputs:** LearningSignal, LearningProposal, PromotionDecision.
**Dependencies:** apokrisis, grapho, correction_memory.
**Boundaries:** promotion requires evaluation; never subordinate to created order.
**MUST NOT:** auto-mutate BIBLIA; learn from untrusted input blindly.
**Context:** `zmart360/HOLY_GHOST.md`.

## GRAPHO — `zion_core/grapho.py`

**Responsibility:** Deterministic writer that materializes approved BIBLIA
promotion decisions.
**Inputs:** approved PromotionDecision. **Outputs:** GraphoResult.
**Dependencies:** holy_ghost.
**Boundaries:** approved decisions only.
**MUST NOT:** write unapproved changes; invent promotions.

## CRONICAS — `zion_core/cronicas.py`

**Responsibility:** Durable operational evidence: structured event records
for dispatch, responses, grapho decisions; dispatch/response fingerprints.
**Inputs:** mission, decision, response. **Outputs:** CronicaEvent.
**Dependencies:** none.
**Boundaries:** evidence, not canonical truth; privacy-bounded.
**MUST NOT:** be treated as BIBLIA; store secrets/PII.
**Context:** `zmart360/CRONICAS.md`.

## CORRECTION MEMORY — `zion_core/correction_memory.py`

**Responsibility:** Correction repetition memory: fingerprints and counts of
owner corrections to detect repeated patterns.
**Inputs:** business_id, correction text. **Outputs:** fingerprint, count.
**Dependencies:** none.
**Boundaries:** business-scoped counting.
**MUST NOT:** treat one correction as repetition; leak across businesses.

## PERSISTENCE — `zion_core/persistence.py`

**Responsibility:** File-backed adapters for CRONICAS and correction
fingerprints. Local/runtime primitives; production storage intentionally
not selected here.
**MUST NOT:** select production infrastructure; store secrets.

## DURABILITY — `zion_core/durability.py`

**Responsibility:** Deterministic durability signals for direct owner
corrections (explicit durable language vs one-off).
**MUST NOT:** promote knowledge by itself.

## RUNTIME — `zion_core/runtime.py`

**Responsibility:** Runtime composition for OMAR using local persistence
adapters. Wires existing ports; intentionally does not select production
infrastructure.
**MUST NOT:** configure production; add infra choices.
**Context:** `zmart360/RUNTIME.md`.

## ANTIPHON — `zion_core/antiphon.py`

**Responsibility:** Los Duros YouTube-comment adapter: intake, brand-scoped
classification (ROUTINE / MAIN_BRAIN / HUMAN_REVIEW per the approved
2026-10-03 routing canon), safety/chotiaera gate, deterministic brand-voiced
reply drafts, write-gated publish intents.
**Inputs:** comment payload, business_id=los-duros.
**Outputs:** NormalizedComment, Classification, ReplyDraft, PublishResult.
**Dependencies:** registry, gates.
**Boundaries:** los-duros only; drafts end at human review; intent only, no transport.
**MUST NOT:** transport HTTP; OAuth; arbitrary tenant resolution; production
writes; invent transcripts.

## GLOSSOLALIA — `zion_core/glossolalia.py`

**Responsibility:** Meta channel adapter: normalize WhatsApp/Instagram/
Facebook events into one canonical event; convert ZION decisions into
channel-validated action intents. Reuses antiphon classification for text.
**Inputs:** raw Meta payload, IntegrationConfig.
**Outputs:** MetaNormalizedEvent, MetaRouteDecision, MetaActionIntent, MetaActionResult.
**Dependencies:** antiphon, registry, gates, omar.
**Boundaries:** integration fixes tenant; write gates default OFF; intent only, no transport.
**MUST NOT:** reason independently of the Brain; choose tenants freely;
real HTTP currently; store secrets.

## PARADOSIS — `zion_core/paradosis.py`

**Responsibility:** Canonical mission context loader: build the shared
MissionPacket, bind it to one tenant (fail closed), seal it against the
repo HEAD, and detect stale context before Builder/commit steps.
**MUST NOT:** call LLMs; perform writes; reach the network; override tenant identity.

## KTEMA — `zion_core/ktema.py`

**Responsibility:** FL property intelligence: county resolution (ZIP and
coordinates against `ktema_county_data.json`), official-source routing via
`PropertySourceRouter`, property-profile normalization, and
`SourceProvenance` tracking — for consumption by authorized businesses.
**Inputs:** PropertyQuery (address/ZIP/coordinates/parcel reference), business_id.
**Outputs:** CountyResolution, PropertyProfile, `to_cronicas_event` dict.
**Dependencies:** registry, cronicas.
**Boundaries:** no HTTP; not SCAN-exclusive (authorized businesses may
consume it); `PARCEL_PATTERNS` ships empty by design; only the fixture
source adapter is published.
**MUST NOT:** call real endpoints; invent parcels or valuations; store PII.
**Status:** Increments 1-4 complete; real source adapters pending schema/
endpoint verification.
**Files:** `zion_core/ktema.py`, `zion_core/ktema_county_data.json`,
`tests/test_zion_ktema_*.py`.
