# ZION CORE Runtime v0.1

The first executable component is the deterministic SAN GABRIEL mission router in `zion_core/router.py`.

## Current boundary
The router validates and routes. It does not execute external tools, deploy, send communications, modify production, grant permissions or mutate BIBLIA.

## Inputs
A mission envelope compatible with `mission_envelope.schema.json`.

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
- command: MICHAEL
- host: MICHAEL.HOST-01
- angel prefix: MICHAEL.HOST-01.ANGEL-

## Next runtime increments
Future increments can add:
1. schema-library validation;
2. SAN PEDRO context lookup;
3. gate interfaces for SERAPHIM / CHERUBIM / THRONES / POWERS;
4. ANGEL allocation;
5. BOOK OF REMEMBRANCE event emission;
6. execution adapters.

These should be added incrementally and must not silently bypass human approval or production safeguards.
