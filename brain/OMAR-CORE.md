# Omar Core

Status: ACTIVE
Owner: Nelson Rivera
System name: Omar
Pronunciation: stress the final syllable.
Written name: Omar, without an accent mark.

## Purpose
Omar is the central source-of-truth gate for Nelson's multi-brand ecosystem. Agents with repository access should consult the relevant project source before work that depends on private brand, automation, system, or asset state.

## Pre-response gate
1. Identify the affected brand, project, system, automation, or asset.
2. Load the relevant repository source before relying on memory or assumptions.
3. For visual work, resolve approved assets before generation.
4. Keep brands isolated; shared tooling does not imply shared ownership.
5. Prefer current repository facts over stale conversational assumptions when they conflict.
6. If a required fact or asset is unresolved, mark it unresolved rather than inventing it.
7. Validate brand mapping, assets, and system status before delivery.

## Repository map
- Zmart AI / central systems: riveranelso/zmart-ai-project
- Zmart Consumer Rights: riveranelso/zmart-consumer-rights
- SCAN Water Intelligence: riveranelso/scan-water-intelligence
- Zero Lag WiFi: riveranelso/zerolag
- Los Duros: riveranelso/LosDuros

## Visual asset source
Canonical multi-brand asset rules:
riveranelso/LosDuros/brain/asset-registry.md

For visual work:
RESOLVE BRAND -> RESOLVE VERIFIED ASSET -> GENERATE WITHOUT FAKE LOGOS -> COMPOSITE VERIFIED LOGO -> VALIDATE -> PASS/REJECT

Never fabricate, redraw, approximate, stylize, or substitute an owned-brand logo. If an approved asset cannot be retrieved, omit the mark rather than generating a replacement. Third-party marks must use verified official vendor assets.

## Brand isolation
- Zmart Consumer Rights is separate from SCAN Water Intelligence.
- Zero Lag WiFi is separate from Zmart Consumer Rights.
- Los Duros is separate from Full Nelson AI.
- Shared tools do not imply shared brand ownership.

## Expected behavior
Nelson should not have to repeat instructions to check GitHub, use the correct logo, retrieve an approved asset, or identify the correct brand when that information is already in the connected source of truth.

## Scope
This gate governs agents and workflows configured to read it or with repository access. External systems still need to be wired to consult this source.

Status: ACTIVE
