# Omar Routing Rules

Status: ACTIVE

Omar is the central router. Business brains remain isolated.

## Runtime sequence
INPUT -> RESOLVE business_id -> BUSINESS-REGISTRY.json -> LOAD project rules -> LOAD approved assets when needed -> EXECUTE -> VALIDATE -> RESPONSE

## Hard rules
- Never route by visual similarity, shared tooling, or memory when business_id or trusted project context is available.
- Unknown business_id: stop and resolve it.
- Missing business_id: resolve only from trusted context; otherwise stop rather than guessing.
- Multi-brand task: load each business separately and validate boundaries before combining output.
- Visual task: load the canonical asset registry before generation.
- A registry entry does not authorize production deployment, endpoint changes, campaign changes, CRM changes, or other runtime mutations.
- Project-specific rules override generic routing behavior for that project.

## Registered routes
- zmart-consumer -> riveranelso/zmart-consumer-rights
- scan -> riveranelso/scan-water-intelligence
- zerolag -> riveranelso/zerolag
- los-duros -> riveranelso/LosDuros

## Known conflict
ZeroLag asset state is unresolved: the central asset registry says an approved branded reference exists, while the ZeroLag repository says no official assets are verified. Until reconciled, Omar must not invent or substitute a ZeroLag logo.
