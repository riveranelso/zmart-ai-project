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
- If CRONICAS already contains a mission decision that never reached `DISPATCH`, APOKRISIS for that mission is rejected; a human-review or denied mission cannot acquire ANGEL authority through `close()`.
- When durable `DISPATCH` evidence exists, `close()` also requires non-empty commission evidence and the responding ANGEL must be one of those recorded commissions; missing or mismatched commission authority fails closed.
- Contradictory durable mission decisions for the same business and mission (for example `DISPATCH` plus a denial/human-review decision) are treated as an integrity conflict and `close()` fails closed.
- A repeated owner correction with the same `correction_id` is a technical retry, not a second human correction.
- The same correction text under a new correction ID may count as a genuine repeated correction.
- These checks survive runtime restart because they use persisted CRONICAS/correction state.
- The local adapter serializes each idempotency critical section with a short-lived operation lock. Dispatch is keyed by business + mission; APOKRISIS by business + mission + ANGEL; owner correction by business + correction ID.
- Correction repetition memory separately serializes updates by business + correction fingerprint so distinct human correction events cannot lose increments.
- Local crash recovery may reclaim a lock only when its recorded owner can be proven dead or its PID can be proven reused through process-start identity. Unknown ownership fails closed by timeout.
- CRONICAS JSONL appends are serialized per physical file across cooperating local processes, flushed and fsynced before the append lock is released. Multiprocess spawn tests verify complete unique records under concurrent writers.
- GRAPHO serializes mutation per physical BIBLIA file and fsyncs the temporary file before atomic replacement. A failed pre-replace write leaves canonical BIBLIA intact and a later retry overwrites stale temporary content. After replacement, parent-directory fsync is best-effort durability hardening and does not turn an already-committed mutation into a retryable failure.
- Persistent correction memory uses the same mandatory fsync-before-replace boundary; a failed pre-replace attempt does not advance the canonical correction count, while post-replace directory-sync failure does not create a false retry.
- These are local-filesystem concurrency guarantees. They are NOT a claim of distributed exactly-once execution.
- A production persistence implementation MUST provide an equivalent atomic uniqueness/transaction boundary across all participating workers before this idempotency contract may be relied on in distributed production.

## Learning and precedence
HOLY GHOST classifies durable lessons to the narrowest valid scope. BIBLIA retrieval order is GLOBAL -> WORKFLOW -> BRAND -> PROJECT -> CAMPAIGN, so more specific active knowledge is presented later and prevails operationally. A narrow-scope override does not delete broader knowledge. Explicit same-scope replacement uses SUPERSEDE only with deterministic candidate mapping; unresolved ambiguity becomes CONFLICT and does not write.

### Normal BIBLIA write boundary
- HOLY GHOST resolves a learning destination through SANPEDRO; OMAR resolves that destination against the configured `biblia_root` before GRAPHO is allowed to write.
- Canonical destination matching uses the exact filename basename for the requested scope. A suffix lookalike is rejected, and more than one registered ref with the same canonical basename is `DESTINATION_AMBIGUOUS` rather than first-match-wins.
- The resolved destination must remain inside `biblia_root`. Registry traversal and authorized-name symlinks that resolve outside the root fail closed with no BIBLIA mutation.
- The ANGEL_RESPONSE remains valid historical evidence when a later BIBLIA destination check fails; no `BIBLIA_MUTATION` event is emitted for the rejected write.
- GRAPHO is the deterministic file materializer, not the business registry or root authority; direct low-level use must be supplied an already-authorized target by its caller.

## Recovery boundary
CRONICAS history is append-only operational evidence. `history()` and `mission_history()` are read-only recovery/observability operations. Reading history never replays dispatch, reruns learning or mutates BIBLIA.

## Safe behavior
Unknown routes, invalid missions, boundary conflicts and applicable gate denials fail closed or require human review. Normal internal automation is not burdened with unnecessary approval friction, while high/critical risk, kill switches and policy/integrity conflicts remain gated.

### ANGEL execution-context integrity
- OMAR binds executable dispatch to the prepared mission, business, SAN PEDRO isolation key, BIBLIA refs, scope, payload, DEREKH route and authorized ANGEL count.
- Decision and commission fields must remain consistent with that prepared authority before execution contexts are created.
- Human-review or gate-denial state blocks execution-context creation.

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

### BIBLIA mutation reconciliation
- If BIBLIA was committed but its `BIBLIA_MUTATION` CRONICAS append failed, OMAR may run explicit reconciliation.
- Reconciliation is verify-and-record only: it MUST NOT replay ANGEL work, owner correction intake, HOLY GHOST learning, or GRAPHO mutation.
- The intended rules must already be proven inside the authorized business section of the target BIBLIA file; otherwise reconciliation fails closed. SANPEDRO must authorize the destination for that business, the destination must remain inside `biblia_root`, the HOLY GHOST scope must match its canonical destination, and only ADD / UPDATE / SUPERSEDE decisions are reconcilable.
- Recovery is serialized by business + mission and is idempotent: an existing mutation event makes subsequent recovery a no-op.
- Reconstructed history is marked `status=RECONCILED` and leaves BIBLIA byte-for-byte unchanged. Reconciliation reads are serialized against GRAPHO writers using the same physical BIBLIA-file lock.
- Direct GRAPHO ADD is idempotent inside the target business section: exact retry does not duplicate a rule, partial retry appends only missing rules, and identical text in another business does not suppress the target business rule.

- Local CRONICAS recovery/history reads serialize snapshot capture against active append using the same physical-file lock; parsing occurs after release, preventing partial active records from being treated as corruption in the cooperating local runtime.

### Local atomic-replace commit boundary
- GRAPHO and persistent correction memory require the temporary file to be flushed and fsynced before atomic replacement; a pre-replace durability failure aborts the operation.
- Once atomic replacement succeeds, the new canonical file is the logical committed state for the live runtime.
- Parent-directory fsync is attempted after replacement as local durability hardening, but an `OSError` at that post-commit step does not convert the already-applied logical commit into a retryable failure.
- This prevents duplicate correction counts or duplicate BIBLIA mutation attempts caused solely by a post-commit metadata-sync error.
- The distinction is local-filesystem behavior and does not claim distributed transaction or power-loss exactly-once semantics.

### Local lock commit boundary
- A local operation lock remains fail-closed while ownership is live, unknown, malformed, or not safely comparable.
- Once a normal release or proven-dead-owner recovery successfully unlinks the lock, that logical unlock is complete; a later directory metadata-sync `OSError` is best-effort durability hardening and does not convert completed protected work into failure.
- Lock unlink failures other than an already-absent file remain significant and are not silently treated as success.

### Response-only learning recovery
- `ANGEL_RESPONSE` is durable evidence that an APOKRISIS arrived; it is not by itself proof that a durable learning cycle completed.
- For durable learning intent, a retry that finds the same business + mission + ANGEL response may re-evaluate HOLY GHOST from the caller-supplied APOKRISIS while suppressing a duplicate `ANGEL_RESPONSE`; mutation evidence from a sibling ANGEL in the same mission must not suppress this ANGEL's recovery.
- If a mutation already exists, or the response has no correction signals, auto-write is disabled, or the learning intent is not durable, the retry remains the normal idempotent no-op.
- Owner-correction recovery follows the same rule but MUST NOT call correction-memory `observe()` again for the same `correction_id`; it reads the existing fingerprint count so a technical retry cannot become a second human correction.
- Recovery uses the existing APOKRISIS supplied on retry and stores no raw correction text in CRONICAS.
- A durable recovery that deterministically resolves to `NO_CHANGE`, `CONFLICT`, or `NOT_READY` has no mutation event by design and may be re-evaluated on another technical retry; this is side-effect-safe but is not modeled as a separate durable terminal learning state.
- New normal GRAPHO mutation events carry the originating ANGEL in `angel_ids`. Recovery may treat a mutation as terminal evidence only when that exact ANGEL is attributed; a sibling ANGEL's mutation and historical/reconciled mutation evidence without origin attribution do not suppress recovery.
### GRAPHO canonical-entry integrity
- Canonical BIBLIA rules written by GRAPHO are single-line entries; proposed or matched rules containing CR/LF are rejected rather than sanitized.
- UPDATE/SUPERSEDE match complete rule lines with exact multiplicity inside the authorized business section; prefixes/substrings are not candidates.
- Identical replacements are byte-preserving no-ops, and real replacements preserve existing line endings/final-newline state outside the replaced rule.
- GRAPHO rejects empty, multiline, or whitespace-padded business IDs so a low-level decision cannot synthesize additional BIBLIA section headings.
