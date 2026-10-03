# ZION CORE — Native Agent Boundary

## Purpose

ZION CORE must own Nelson-specific operating intelligence without rebuilding generic coding-agent infrastructure already supplied by the development platform.

## KEEP IN ZION

These are ZION-owned semantics and remain canonical:

- BIBLIA: current durable knowledge and operating rules.
- CRONICAS: privacy-bounded event/history evidence.
- HOLY GHOST: reusable-learning classification and promotion semantics.
- OMAR: owner-facing operational composition.
- SAN PEDRO: business/context registry and isolation authority.
- GRAPHO: deterministic canonical BIBLIA mutation semantics.
- Business isolation and scope precedence.
- Durable correction identity, retry semantics, and recovery evidence.
- Brand/project/workflow rules that encode Nelson's actual operating methods.

## USE NATIVE PLATFORM CAPABILITIES

Do not build ZION runtime substitutes for:

- codebase exploration;
- general software implementation agents;
- independent code review agents;
- security code review agents;
- test-running agents;
- parallel/subagent context management;
- generic skill discovery/loading;
- generic MCP tool connectivity;
- deterministic development hooks;
- CI execution and ordinary build/test orchestration.

Use repository agent profiles in `.github/agents/`, reusable skills in `.agents/skills/`, CI, hooks, MCP, and supported platform subagent orchestration instead.

## CURRENT DEVELOPMENT TEAM

- `zion-builder`: focused implementation.
- `zion-adversarial`: failure-mode and adversarial testing.
- `zion-reviewer`: independent regression/isolation/privacy review.
- `zion-architect`: research and build-vs-native boundary decisions.

All share the canonical ZION development contract through `.agents/skills/zion-development/SKILL.md`.

## DECISION RULE

Before creating a new development-oriented runtime component:

1. Check for a native platform capability.
2. Check for an existing skill.
3. Check whether a custom/subagent is sufficient.
4. Check whether a deterministic hook or CI step is sufficient.
5. Check whether MCP/tool integration is sufficient.
6. Only implement custom ZION runtime code when the capability depends on ZION-owned state or semantics.

## DO NOT REMOVE BLINDLY

Existing ZION persistence, learning, isolation, and recovery code is not generic developer scaffolding merely because an agent can edit code. Removal requires demonstrated semantic equivalence and regression tests.

## PRODUCTION BOUNDARY

Agent automation does not grant deployment authority. Production deploys, main-branch merges, destructive changes, secrets/permissions changes, and customer-data operations remain explicit owner-approval boundaries.
