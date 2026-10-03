# ZION CORE Runtime v0.2

The executable dispatch process is EXAPOSTELLO in `zion_core/router.py`. EXAPOSTELLO is the SAN GABRIEL act of sending an authorized MEGILLAH toward its resolved COMMAND/HOST. `route_mission()` remains only as a compatibility alias.

## Current boundary
The runtime validates, prepares, dispatches and records bounded ZION work. It does not execute arbitrary external tools, deploy, modify production infrastructure, grant permissions or treat CRONICAS as canonical truth.

## Canonical inputs and routing
- Mission contract: `zmart360/megillah.schema.json`.
- Dispatch path authority: `zmart360/derekh.yaml`.
- Business/context authority: SANPEDRO registry.
- Canonical knowledge: BIBLIA, retrieved broadest to most specific.
- Legacy `mission_envelope.schema.json` and `dispatch_routes.yaml` remain compatibility debt only.

## OMAR runtime composition
`zion_core.runtime.OmarRuntime` composes the existing ports with local persistence adapters:
- BIBLIA retrieval;
- EXAPOSTELLO dispatch;
- CRONICAS JSONL event history;
- persistent correction fingerprints/counts;
- owner-correction learning;
- APOKRISIS close/learning;
- read-only mission history.

Production storage is intentionally not selected by this composition.

## Idempotency
- A repeated `business_id + mission_id` dispatch becomes `IDEMPOTENT_NOOP` and does not append a second MISSION_DECISION.
- A repeated APOKRISIS from the same `business_id + mission_id + angel_id` is not processed twice.
- A repeated owner correction with the same `correction_id` is a technical retry, not a second human correction.
- The same correction text under a new correction ID may count as a genuine repeated correction.
- These checks survive runtime restart because they use persisted CRONICAS/correction state.
- The local adapter serializes each idempotency critical section with a short-lived operation lock. Dispatch is keyed by business + mission; APOKRISIS by business + mission + ANGEL; owner correction by business + correction ID.
- Correction repetition memory separately serializes updates by business + correction fingerprint so distinct human correction events cannot lose increments.
- Local crash recovery may reclaim a lock only when its recorded owner can be proven dead or its PID can be proven reused through process-start identity. Unknown ownership fails closed by timeout.
- These are local-filesystem concurrency guarantees. They are NOT a claim of distributed exactly-once execution.
- A production persistence implementation MUST provide an equivalent atomic uniqueness/transaction boundary across all participating workers before this idempotency contract may be relied on in distributed production.

## Learning and precedence
HOLY GHOST classifies durable lessons to the narrowest valid scope. BIBLIA retrieval order is GLOBAL -> WORKFLOW -> BRAND -> PROJECT -> CAMPAIGN, so more specific active knowledge is presented later and prevails operationally. A narrow-scope override does not delete broader knowledge. Explicit same-scope replacement uses SUPERSEDE only with deterministic candidate mapping; unresolved ambiguity becomes CONFLICT and does not write.

## Recovery boundary
CRONICAS history is append-only operational evidence. `history()` and `mission_history()` are read-only recovery/observability operations. Reading history never replays dispatch, reruns learning or mutates BIBLIA.

## Safe behavior
Unknown routes, invalid missions, boundary conflicts and applicable gate denials fail closed or require human review. Normal internal automation is not burdened with unnecessary approval friction, while high/critical risk, kill switches and policy/integrity conflicts remain gated.

## Current implementation
- SANPEDRO context resolution
- BIBLIA isolated retrieval and explicit scope precedence
- SERAPHIM / CHERUBIM / THRONES / POWERS gates
- EXAPOSTELLO routing
- DIATASSO ANGEL commissioning
- APOKRISIS responses
- CRONICAS emission, JSONL persistence and scoped read-only history
- HOLY GHOST learning decisions
- GRAPHO ADD / UPDATE / SUPERSEDE mutation
- persistent correction repetition memory
- OMAR composed runtime and idempotency

## Not production deployment
This branch is architecture/runtime work only. No production backend, n8n, Fly deployment, customer traffic or `main` branch is changed by these runtime documents.
