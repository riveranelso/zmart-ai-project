# SAN PEDRO — ZION CORE Registry & Keys

SAN PEDRO is the authoritative registry for locating trusted ZION CORE context.

It knows which businesses and work areas exist and where their canonical knowledge lives. The machine-readable registry is `san_pedro_registry.json`.

## Runtime contract
Before SAN GABRIEL may return DISPATCH, SAN PEDRO must resolve the mission's `business_id`.

Resolution returns:
- canonical business ID;
- display name;
- isolation key;
- canonical context references.

Unknown, disabled or contextless businesses fail closed to human review.

### Compatibility aliases
Some business IDs are contractual in external runtimes and cannot be renamed. ZION keeps ONE canonical identity per business; legacy IDs are mapped once at ingress and every downstream artifact carries only the canonical identity.

Current aliases:
- `zerolag` → `zero-lag-wifi` (Omar Core's `brain/BUSINESS-REGISTRY.json`, router, and tests use `zerolag`; ZION's canonical identity is `zero-lag-wifi`).

A claimed `zerolag` therefore resolves to the same `BusinessContext` (canonical ID, isolation key, context refs) as `zero-lag-wifi`. Post-resolution tenant checks keep using the canonical ID and fail closed on any mismatch — the alias does not create a second identity.

For canonical learning destinations, the registered reference must match the scope's canonical BIBLIA filename by exact basename. Suffix lookalikes are not authorization. Zero matches remain unregistered; multiple matches for the same canonical basename are ambiguous and fail closed rather than selecting one by order.

## Registered work areas
- Zmart Consumer Rights
- SCAN Water Intelligence / ScanTapWater
- Los Duros
- Yek Family
- Zero Lag WiFi
- Zmart Home Solutions
- Full Nelson AI
- Zmart AI / Jessica

## Isolation
A successful lookup does not authorize cross-business access. The returned isolation key follows the mission through routing so downstream layers can enforce separation.

## Boundaries
SAN PEDRO locates and identifies. It does not execute ANGEL work, grant permissions, dispatch missions, or perform HOLY GHOST learning.

## Relationship
- HOLY GHOST guides and learns.
- OMAR interprets and coordinates.
- SAN PEDRO resolves trusted context.
- BIBLIA contains canonical durable knowledge.
- SAN GABRIEL dispatches authorized missions.
- ANGELS execute bounded work.
