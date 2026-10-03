# ZION CORE Runtime v0.1

The first executable dispatch process is EXAPOSTELLO in `zion_core/router.py`. EXAPOSTELLO is the SAN GABRIEL act of sending an authorized mission toward its resolved COMMAND/HOST. The legacy `route_mission()` name remains only as a compatibility alias during migration.

## Current boundary
EXAPOSTELLO validates and dispatches routing decisions. It does not execute external tools, deploy, send communications, modify production, grant permissions or mutate BIBLIA.

## Inputs
A MEGILLAH compatible with `megillah.schema.json`. The legacy `mission_envelope.schema.json` remains temporarily for compatibility.

## Routing source
`dispatch_routes.yaml` is the route authority for this runtime.

## Safe behavior
- Unknown intent -> REQUIRE_HUMAN_REVIEW / ROUTE_NOT_FOUND
- Requested command conflicts with canonical route -> REQUIRE_HUMAN_REVIEW
- Requested host conflicts with canonical route -> REQUIRE_HUMAN_REVIEW
- Explicit human approval requirement -> REQUIRE_HUMAN_REVIEW
- High or critical risk -> REQUIRE_HUMAN_REVIEW
- Invalid mission -> rejected
- Duplicate/invalid route registry -> fail closed

## Output
A DispatchDecision containing action, reason, command, host and ANGEL identity prefix when dispatch is permitted.

## Example
Input intent: `threat_detection`

Decision:
- command: SANMIGUEL
- host: SANMIGUEL.HOST-01
- angel prefix: SANMIGUEL.HOST-01.ANGEL-

## Implemented runtime layers
- SAN PEDRO context lookup
- SERAPHIM / CHERUBIM / THRONES / POWERS admission gates
- ANGEL allocation
- CRONICAS event model (persistence/wiring remains a later increment)

## Remaining increments
- schema-library validation;
- CRONICAS runtime event emission/persistence;
- execution adapters;
- deliberate migration of remaining generic ZION-owned names under the global naming law.

These should be added incrementally and must not silently bypass human approval or production safeguards.
