# CRÓNICAS — ZION CORE Historical Record

CRÓNICAS is ZION CORE's structured historical record of operational events, decisions, blocks, corrections and learning evidence.

CRÓNICAS is not canonical truth. BIBLIA remains the source of current canonical knowledge.

## Relationship
CRÓNICAS -> HOLY GHOST -> BIBLIA

HOLY GHOST may use durable patterns and corrections recorded in CRÓNICAS as evidence when deciding whether a lesson should be promoted into BIBLIA. Promotion must still follow scope, integrity, security and authority rules.

## What CRÓNICAS records
- mission routing decisions;
- gate denials and their reason codes;
- successful ANGEL allocation/dispatch decisions;
- meaningful correction and learning signals;
- runtime failures relevant to future repair.

## Privacy boundary
CRÓNICAS must not store passwords, API keys, tokens, customer PII, private lead records or raw sensitive payloads. Store references and minimal operational metadata instead.

## Technical ID
CRONICAS


## Runtime persistence and recovery
The current local runtime adapter persists privacy-bounded events as JSON Lines. CRONICAS can be queried by business, event type or mission while preserving append order.

History reads are observational only. They do not replay a mission, re-run an ANGEL, re-run HOLY GHOST, or mutate BIBLIA.

CRONICAS also provides durable evidence for runtime idempotency:
- an existing MISSION_DECISION prevents duplicate dispatch of the same business/mission identity;
- an existing ANGEL_RESPONSE prevents duplicate processing of the same business/mission/ANGEL response;
- an existing OMAR.OWNER-INPUT response for a correction ID prevents a technical retry from being counted as a second human correction.

Corrupt persisted history fails closed with the affected line number rather than silently skipping evidence.

Local JSONL append integrity is protected by a short-lived per-file filesystem lock. Each completed append is flushed and fsynced before the lock is released. Thread and spawned-process concurrency tests verify that cooperating local writers produce complete, parseable, unique records.

This is a local-filesystem persistence guarantee only. It does not provide distributed exactly-once semantics across hosts or independent storage systems.

### Reconciled BIBLIA mutation evidence
- `BIBLIA_MUTATION` may use `status=RECONCILED` only when recovery proves the intended rules are already present in the authorized business section but the original mutation event is missing. The target must also be SANPEDRO-authorized, contained under BIBLIA, consistent with the decision scope, and associated with a mutating ADD / UPDATE / SUPERSEDE action.
- RECONCILED is historical repair, not a new mutation and not a replay of the ANGEL or owner correction.
- Reconciliation is idempotent and serialized by business + mission; concurrent attempts produce at most one recovered mutation event in the local runtime.

### Snapshot reads during local writes
- Local CRONICAS readers acquire the same per-file append lock as writers only long enough to capture a complete text snapshot.
- Parsing and filtering happen after the lock is released.
- A reader therefore does not interpret an actively written partial final record as persisted corruption under the cooperating local adapter.
- Lock timeout remains fail-closed; this is a local-filesystem guarantee, not distributed snapshot isolation.

- For local atomic replacements used by BIBLIA/correction state, pre-replace file fsync remains mandatory; post-replace directory fsync is durability hardening and does not redefine an already-visible logical commit as failed. CRONICAS recovery must continue to distinguish historical evidence from canonical state.

### GRAPHO retry evidence
- An idempotent ADD retry that finds every proposed rule already present in the target business section does not mutate BIBLIA and is historical `status=UNCHANGED`, not `CHANGED`.
- Partial ADD retry writes only missing rules in that business section; identical rule text in another business is not treated as evidence for the target business.

### Response-only learning recovery
- An existing `ANGEL_RESPONSE` proves receipt, not necessarily completion of later HOLY GHOST/GRAPHO work.
- Durable retry recovery suppresses a duplicate response event and may produce the missing `BIBLIA_MUTATION` only if the re-evaluated learning cycle actually writes.
- The retry uses the caller-supplied APOKRISIS; CRONICAS continues to store privacy-bounded metadata rather than raw correction text.
- Owner retries preserve the original correction fingerprint count; recovery of the same `correction_id` is not new human evidence.
- Non-mutating terminal evaluations do not manufacture `BIBLIA_MUTATION` evidence.
- New normal `BIBLIA_MUTATION` events attribute the originating APOKRISIS/owner input in `angel_ids` without storing rule text. Reconciliation does not invent an origin when it cannot prove one. Same-ANGEL attribution may support retry idempotency; sibling or unattributed mutation evidence must not be used as proof that another ANGEL's learning completed.
