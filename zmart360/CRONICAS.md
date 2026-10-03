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
