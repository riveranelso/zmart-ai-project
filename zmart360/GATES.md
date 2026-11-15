# ZION CORE Executable Gates

Before SAN GABRIEL may return DISPATCH, a resolved mission passes four fail-closed admission gates.

## SERAPHIM — Integrity
Checks that canonical context exists and rejects declared integrity conflicts.

## CHERUBIM — Security & Boundaries
Checks business isolation and authorization signals. A requested isolation key may not differ from SAN PEDRO's canonical isolation key.

## THRONES — Authority & Policy
Stops missions requiring human approval or carrying a declared policy conflict.

## POWERS — Runtime Enforcement
Stops high/critical-risk automatic dispatch, disabled runtime, or an active kill switch.

## Rule
A single denied gate prevents ANGEL dispatch. Gate denial returns REQUIRE_HUMAN_REVIEW with the denying gate and reason.

These gates are admission controls only. They do not execute external actions or claim to replace downstream authentication, authorization, policy engines, sandboxing, rate limiting or production controls.
