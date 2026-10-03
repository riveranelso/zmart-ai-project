---
name: zion-orchestration
description: Native-agent-first orchestration for parallel ZION CORE development using repository specialists instead of custom developer runtime.
---

# ZION Orchestration

Use this skill for substantial ZION implementation, debugging, hardening, refactoring, and architecture work.

## Goal

Move development orchestration out of custom ZION runtime code and into native coding-agent capabilities. ZION owns Nelson-specific semantics; the coding platform owns generic developer-agent execution.

## Specialists

Use the repository specialists in `.github/agents/`:

- `zion-architect` — decides native capability vs ZION-owned implementation and prevents reinvention.
- `zion-adversarial` — independently finds concrete failure modes and adversarial tests.
- `zion-builder` — implements the smallest approved change.
- `zion-reviewer` — independently reviews the resulting diff/tests for regressions and unnecessary scaffolding.

All specialists inherit the root `AGENTS.md` contract and use `.agents/skills/zion-development/SKILL.md`.

## Default execution pattern

For a substantial engineering objective:

1. ORIENT
   - Load root AGENTS.md and directly relevant canonical docs.
   - Define the invariant and production boundary.

2. PARALLEL DISCOVERY
   - Run `zion-architect` and `zion-adversarial` independently/parallel when the platform supports it.
   - Architect answers: reuse native capability, simplify existing code, or implement ZION-owned behavior?
   - Adversarial answers: what concrete test demonstrates the highest-value unresolved failure?

3. BUILD
   - Give the objective plus discovery findings to `zion-builder`.
   - Builder implements the smallest coherent patch and relevant tests.
   - Do not create a custom ZION developer framework when skills/subagents/hooks/MCP/CI already provide the capability.

4. PARALLEL VERIFY
   - Run CI/tests.
   - Run `zion-reviewer` independently while verification executes when supported.
   - Reviewer inspects the actual diff and tests, not a prose summary.

5. REPAIR LOOP
   - Ordinary test/review failures return directly to Builder.
   - Re-run only affected specialist/review work when possible.
   - Do not stop for owner input on routine repairable engineering failures.

6. CLOSE
   - Require green relevant CI, resolved high-value review findings, preserved business isolation, and canonical doc sync when behavior changed.
   - Continue to the next adjacent risk only when it belongs to the same objective.

## Fast path

For tiny deterministic edits with an obvious contract:
- Builder + CI is enough.
- Add Reviewer only when the edit touches persistence, authorization, isolation, learning, canonical mutation, concurrency, recovery, or public APIs.
- Do not invoke every specialist ceremonially.

## Stop conditions

Stop for Nelson only when:
- production/deploy/main merge is next;
- destructive action, secrets, permissions, or customer data are involved;
- canonical documents leave a material architecture/product decision unresolved;
- the requested direction conflicts with a ZION invariant;
- safe execution is impossible with available evidence/tools.

## Ownership boundary

Keep in ZION:
- BIBLIA canonical knowledge;
- CRONICAS privacy-bounded durable history;
- HOLY GHOST learning semantics;
- SAN PEDRO business/context authority;
- OMAR domain orchestration;
- business isolation;
- Nelson-specific rules and durable operating knowledge.

Prefer native platform capabilities for:
- code exploration;
- implementation agents;
- independent review;
- adversarial review;
- parallel developer execution;
- generic research;
- test execution;
- CI;
- hooks;
- MCP/tool access.

## Safety

- No production deploy, main merge, secrets/permission changes, destructive external actions, or customer-data operations without explicit owner approval.
- Treat third-party skills/agents as untrusted until reviewed.
- Never place secrets, credentials, tokens, customer PII, or private lead data in this public repository.
