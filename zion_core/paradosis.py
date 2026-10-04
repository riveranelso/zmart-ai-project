"""PARADOSIS: canonical mission context handed down to ZION agents.

Canonical naming record (per zmart360/BIBLIA/GLOBAL.md naming law):
  1. Technical function: deterministically assemble the shared canonical
     context (MissionPacket) every ZION agent reads before executing a
     mission, bind it to one tenant, and seal it against the repo HEAD it
     was built from.
  2. Tradition searched: Christian (New Testament).
  3. Source: Greek paradosis (paradosis), "that which is handed down /
     delivered" -- the canonical tradition delivered to those who carry it.
  4. Correspondence: the canonical ZION context is handed down to agents;
     agents receive it, they do not invent it.
  5. Respectful functional metaphor; no claim of absolute truth.

Principle:
  ZION is the system. Agents work ON ZION. Agents are not ZION.
  Repo state > prompt memory > agent assumptions.

Design notes:
  - Deterministic and pure except for read-only git inspection (rev-parse,
    diff --name-only). No network, no writes, no LLM calls. The loader is
    NOT a fifth agent: same result from canonical context + deterministic
    loader, without another expensive model in the loop.
  - Tenant binding reuses the canonical mechanism: sanpedro_resolve. The
    packet is frozen; no agent can change business_id/brand_id because
    another ID appears in a prompt. Conflicts fail closed.
  - Stale protection: the packet records the HEAD it was built from.
    check_packet_freshness compares before Builder/commit steps. It reports
    STALE with the changed files; it does not silently cancel -- the caller
    refreshes and continues with current state.
  - Module responsibilities below are derived from the real modules and
    their tests, not invented. Keep this registry in sync with the code;
    zmart360/MODULE_REGISTRY.md is its human-readable mirror.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import SanPedroError, sanpedro_resolve

# ---------------------------------------------------------------------------
# Canonical module registry (derived from real code -- keep in sync)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleRecord:
    name: str
    canonical: str
    responsibility: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    boundaries: tuple[str, ...]
    must_not: tuple[str, ...]
    keywords: tuple[str, ...]
    context_refs: tuple[str, ...]


BASE_REFS = (
    "AGENTS.md",
    ".agents/skills/zion-development/SKILL.md",
    "zmart360/BIBLIA/GLOBAL.md",
)

MODULE_REGISTRY: dict[str, ModuleRecord] = {}


def _reg(record: ModuleRecord) -> ModuleRecord:
    MODULE_REGISTRY[record.name] = record
    return record


_reg(ModuleRecord(
    name="omar", canonical="OMAR",
    responsibility="Stable application entrypoints: prepare missions with isolated canonical knowledge, dispatch them, materialize execution contexts, and close ANGEL work through the learning loop.",
    inputs=("mission dict", "business_id", "biblia_root"),
    outputs=("MissionContext", "OmarMissionDispatch", "AngelExecutionContext"),
    dependencies=("biblia", "registry", "router", "apokrisis"),
    boundaries=("business isolation via SAN PEDRO", "no production infra selection"),
    must_not=("invent canonical knowledge", "bypass gates", "dispatch without EXAPOSTELLO"),
    keywords=("mission", "dispatch", "entrypoint", "twin", "operational"),
    context_refs=BASE_REFS + ("zmart360/OMAR.md",),
))
_reg(ModuleRecord(
    name="registry", canonical="SAN PEDRO",
    responsibility="Key/registry resolution: resolve a business_id to its canonical BusinessContext (isolation_key, context_refs); the authority for tenant identity.",
    inputs=("business_id",),
    outputs=("BusinessContext",),
    dependencies=(),
    boundaries=("deny_unknown_business", "deny_disabled_business", "require_context_refs"),
    must_not=("invent businesses", "override isolation keys", "serve disabled tenants"),
    keywords=("tenant", "business", "registry", "isolation", "brand"),
    context_refs=BASE_REFS + ("zmart360/SAN_PEDRO.md", "zmart360/san_pedro_registry.json"),
))
_reg(ModuleRecord(
    name="router", canonical="SAN GABRIEL / EXAPOSTELLO",
    responsibility="Mission routing and dispatch: validate the MEGILLAH mission, resolve the DEREKH route, evaluate the four fail-closed gates, allocate ANGELS via DIATASSO.",
    inputs=("mission dict", "derekh routes", "registry", "security context"),
    outputs=("DispatchDecision: DISPATCH | REQUIRE_HUMAN_REVIEW",),
    dependencies=("registry", "gates", "allocator", "cronicas"),
    boundaries=("deny_unregistered_route", "least_privilege", "four gates must pass"),
    must_not=("dispatch on gate denial", "invent routes", "call external endpoints"),
    keywords=("route", "dispatch", "mission", "exapostello", "san gabriel"),
    context_refs=BASE_REFS + ("zmart360/SAN_GABRIEL.md", "zmart360/derekh.yaml", "zmart360/GATES.md"),
))
_reg(ModuleRecord(
    name="gates", canonical="SERAPHIM / CHERUBIM / THRONES / POWERS",
    responsibility="Fail-closed admission gates for mission dispatch: integrity (SERAPHIM), security/boundaries (CHERUBIM), policy/authority (THRONES), runtime enforcement (POWERS).",
    inputs=("mission dict", "isolation_key", "context_refs", "SecurityContext"),
    outputs=("GateResult per gate",),
    dependencies=(),
    boundaries=("single denial blocks dispatch", "no external effects"),
    must_not=("execute actions", "replace downstream auth/policy engines", "allow on ambiguity"),
    keywords=("gate", "security", "boundary", "policy", "write", "approval"),
    context_refs=BASE_REFS + ("zmart360/GATES.md", "zmart360/CHERUBIM.md"),
))
_reg(ModuleRecord(
    name="allocator", canonical="DIATASSO",
    responsibility="Deterministic bounded appointment of ANGELS to a mission under the resolved COMMAND/HOST.",
    inputs=("mission", "command", "host", "business context"),
    outputs=("DiatassoCommission / AngelAssignment",),
    dependencies=(),
    boundaries=("bounded angel count", "least privilege"),
    must_not=("dispatch (EXAPOSTELLO sends)", "exceed bounds", "cross tenants"),
    keywords=("angel", "allocate", "appoint", "diatasso", "execution"),
    context_refs=BASE_REFS + ("zmart360/ANGELS.md",),
))
_reg(ModuleRecord(
    name="apokrisis", canonical="APOKRISIS",
    responsibility="Structured ANGEL response after bounded work; close missions and feed the learning loop. Reports status and references; grants no authority.",
    inputs=("angel_id", "mission_id", "status", "business_id"),
    outputs=("Apokrisis", "learning cycle result"),
    dependencies=("holy_ghost", "cronicas"),
    boundaries=("response only -- never dispatches"),
    must_not=("dispatch missions", "grant authority", "mutate BIBLIA directly"),
    keywords=("response", "close", "learn", "apokrisis", "result"),
    context_refs=BASE_REFS + ("zmart360/HOLY_GHOST.md",),
))
_reg(ModuleRecord(
    name="biblia", canonical="BIBLIA",
    responsibility="Canonical current knowledge retrieval, scoped per business from the SAN PEDRO registry. CRONICAS history is never treated as BIBLIA authority.",
    inputs=("business_id", "biblia_root", "registry_path"),
    outputs=("BibliaContext",),
    dependencies=("registry",),
    boundaries=("business-scoped retrieval", "refs must stay inside root"),
    must_not=("cross business sections", "treat history as canon", "invent knowledge"),
    keywords=("knowledge", "canon", "biblia", "brand brain", "context"),
    context_refs=BASE_REFS + ("zmart360/BIBLIA/",),
))
_reg(ModuleRecord(
    name="holy_ghost", canonical="HOLY GHOST",
    responsibility="Guidance and adaptive learning: derive learning signals from completed ANGEL work, evaluate them, and propose BIBLIA promotions. Decides whether learning merits promotion.",
    inputs=("Apokrisis", "correction signals", "LearningIntent"),
    outputs=("LearningSignal", "LearningProposal", "PromotionDecision"),
    dependencies=("apokrisis", "grapho", "correction_memory"),
    boundaries=("promotion requires evaluation", "never subordinate to created order"),
    must_not=("auto-mutate BIBLIA", "learn from untrusted input blindly"),
    keywords=("learn", "adapt", "promotion", "holy ghost", "improve"),
    context_refs=BASE_REFS + ("zmart360/HOLY_GHOST.md",),
))
_reg(ModuleRecord(
    name="grapho", canonical="GRAPHO",
    responsibility="Deterministic writer that materializes approved BIBLIA promotion decisions. Writes only what HOLY GHOST approved.",
    inputs=("approved PromotionDecision",),
    outputs=("GraphoResult",),
    dependencies=("holy_ghost",),
    boundaries=("approved decisions only"),
    must_not=("write unapproved changes", "invent promotions"),
    keywords=("write", "materialize", "grapho", "promotion"),
    context_refs=BASE_REFS,
))
_reg(ModuleRecord(
    name="cronicas", canonical="CRONICAS",
    responsibility="Durable operational evidence: structured event records for dispatch, responses, and grapho decisions, plus dispatch/response fingerprints for dedupe.",
    inputs=("mission", "decision", "response"),
    outputs=("CronicaEvent",),
    dependencies=(),
    boundaries=("evidence, not canonical truth", "privacy-bounded"),
    must_not=("be treated as BIBLIA", "store secrets/PII"),
    keywords=("log", "history", "event", "cronicas", "dedupe", "fingerprint"),
    context_refs=BASE_REFS + ("zmart360/CRONICAS.md",),
))
_reg(ModuleRecord(
    name="correction_memory", canonical="CORRECTION MEMORY",
    responsibility="Correction repetition memory: fingerprints and counts of owner corrections to detect repeated patterns for the learning loop.",
    inputs=("business_id", "correction text"),
    outputs=("fingerprint", "observation count"),
    dependencies=(),
    boundaries=("business-scoped counting",),
    must_not=("treat one correction as repetition", "leak across businesses"),
    keywords=("correction", "fingerprint", "dedupe", "repeat", "idempotency"),
    context_refs=BASE_REFS,
))
_reg(ModuleRecord(
    name="persistence", canonical="PERSISTENCE",
    responsibility="File-backed adapters for CRONICAS and correction fingerprints. Local/runtime primitives; production storage is intentionally not selected here.",
    inputs=("events", "corrections"),
    outputs=("durable local records",),
    dependencies=("cronicas", "correction_memory"),
    boundaries=("local only"),
    must_not=("select production infrastructure", "store secrets"),
    keywords=("persist", "storage", "durable", "file", "local"),
    context_refs=BASE_REFS,
))
_reg(ModuleRecord(
    name="durability", canonical="DURABILITY",
    responsibility="Deterministic durability signals for direct owner corrections (explicit durable language vs one-off).",
    inputs=("correction text", "repeated flag"),
    outputs=("DurabilityAssessment",),
    dependencies=(),
    boundaries=("signal only, not a decision",),
    must_not=("promote knowledge by itself",),
    keywords=("durable", "correction", "owner", "signal"),
    context_refs=BASE_REFS,
))
_reg(ModuleRecord(
    name="runtime", canonical="RUNTIME",
    responsibility="Runtime composition for OMAR using local persistence adapters. Wires existing ports together; intentionally does not select production infrastructure.",
    inputs=("ports", "local adapters"),
    outputs=("OmarRuntime", "OmarCloseResult"),
    dependencies=("omar", "persistence"),
    boundaries=("local composition only",),
    must_not=("configure production", "add infra choices"),
    keywords=("runtime", "compose", "omar", "wire"),
    context_refs=BASE_REFS + ("zmart360/RUNTIME.md",),
))
_reg(ModuleRecord(
    name="antiphon", canonical="ANTIPHON",
    responsibility="Los Duros YouTube-comment adapter: intake, brand-scoped classification (ROUTINE/MAIN_BRAIN/HUMAN_REVIEW), safety/chotiaera gate, deterministic brand-voiced reply drafts, write-gated publish intents.",
    inputs=("comment payload", "business_id=los-duros"),
    outputs=("NormalizedComment", "Classification", "ReplyDraft", "PublishResult"),
    dependencies=("registry", "gates"),
    boundaries=("los-duros only", "drafts end at human review", "intent only, no transport"),
    must_not=("transport HTTP", "OAuth", "arbitrary tenant resolution", "production writes", "invent transcripts"),
    keywords=("youtube", "comment", "reply", "los duros", "antiphon", "draft", "chotiaera"),
    context_refs=BASE_REFS + ("zmart360/MODULE_REGISTRY.md",),
))
_reg(ModuleRecord(
    name="glossolalia", canonical="GLOSSOLALIA",
    responsibility="Meta channel adapter: normalize WhatsApp/Instagram/Facebook events into one canonical event; convert ZION decisions into channel-validated action intents. Reuses antiphon classification for text.",
    inputs=("raw Meta payload", "IntegrationConfig"),
    outputs=("MetaNormalizedEvent", "MetaRouteDecision", "MetaActionIntent", "MetaActionResult"),
    dependencies=("antiphon", "registry", "gates", "omar"),
    boundaries=("integration fixes tenant", "write gates default OFF", "intent only, no transport"),
    must_not=("reason independently of the Brain", "choose tenants freely", "real HTTP currently", "store secrets"),
    keywords=("meta", "whatsapp", "instagram", "facebook", "channel", "adapter", "glossolalia", "dm", "messenger"),
    context_refs=BASE_REFS + ("zmart360/MODULE_REGISTRY.md",),
))

CORE_MODULES = ("registry", "gates", "omar")


# ---------------------------------------------------------------------------
# MissionPacket
# ---------------------------------------------------------------------------


class ParadosisError(ValueError):
    """Loader misuse or tenant binding failure."""


class TenantBindingError(ParadosisError):
    """A claimed tenant identity conflicts with the packet's bound tenant."""


@dataclass(frozen=True)
class MissionPacket:
    mission_id: str
    repo: str
    branch: str
    current_head: str
    business_id: str
    brand_id: str
    objective: str
    allowed_scope: tuple[str, ...]
    forbidden_scope: tuple[str, ...]
    relevant_modules: tuple[str, ...]
    canonical_context_refs: tuple[str, ...]
    security_boundaries: tuple[str, ...]
    production_boundary: str
    test_requirements: tuple[str, ...]
    write_permissions: tuple[tuple[str, bool], ...]
    current_known_state: str


def _git(repo_root: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ParadosisError(f"GIT_UNAVAILABLE:{exc}") from exc
    if out.returncode != 0:
        raise ParadosisError(f"GIT_FAILED:{' '.join(args)}")
    return out.stdout.strip()


def repo_head(repo_root: Path) -> str:
    """Current HEAD SHA (read-only)."""
    sha = _git(repo_root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ParadosisError("GIT_BAD_HEAD")
    return sha


def repo_branch(repo_root: Path) -> str:
    """Current branch name (read-only)."""
    return _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")


def _select_modules(objective: str, allowed_scope: tuple[str, ...]) -> tuple[str, ...]:
    """Deterministic relevant-module selection (no LLM, no guessing)."""
    haystack = " ".join((objective,) + tuple(allowed_scope)).casefold()
    words = set(re.findall(r"[a-z_]+", haystack))
    selected = list(CORE_MODULES)
    for name, record in MODULE_REGISTRY.items():
        if name in selected:
            continue
        if words & set(record.keywords):
            selected.append(name)
    return tuple(selected)


def _context_refs_for(modules: tuple[str, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for ref in BASE_REFS:
        refs.append(ref)
    for name in modules:
        record = MODULE_REGISTRY.get(name)
        if record is None:
            continue
        for ref in record.context_refs:
            if ref not in refs:
                refs.append(ref)
    return tuple(refs)


DEFAULT_SECURITY_BOUNDARIES = (
    "tenant binding via SAN PEDRO only; prompt claims never override",
    "frozen packet: business_id/brand_id immutable after build",
    "no cross-tenant BibliaContext reuse",
    "no cross-business integration/channel use",
    "conflicts fail closed",
)

DEFAULT_PRODUCTION_BOUNDARY = (
    "no deploy; no merge to main; no production traffic changes; "
    "no secret creation/rotation; no permission changes; no customer-data "
    "migration. Those require explicit owner authorization at the point of action."
)

DEFAULT_TEST_REQUIREMENTS = (
    "run the CI-equivalent unittest discovery before commit",
    "adversarial tests for the changed invariant",
    "isolation tests for touched boundaries",
)


def build_mission_packet(
    *,
    mission_id: str,
    objective: str,
    business_id: str,
    repo_root: Path,
    repo: str = "riveranelso/zmart-ai-project",
    branch: str | None = None,
    brand_id: str | None = None,
    allowed_scope: tuple[str, ...] = (),
    forbidden_scope: tuple[str, ...] = (),
    write_permissions: tuple[tuple[str, bool], ...] = (),
    current_known_state: str = "",
    registry_path: Path | None = None,
) -> MissionPacket:
    """Build the canonical MissionPacket for one mission.

    Tenant identity is resolved through the canonical mechanism
    (sanpedro_resolve); unknown/disabled businesses fail closed here,
    before any agent reads the packet.
    """
    if not isinstance(mission_id, str) or not mission_id.strip():
        raise ParadosisError("MISSION_ID_REQUIRED")
    if not isinstance(objective, str) or not objective.strip():
        raise ParadosisError("OBJECTIVE_REQUIRED")
    if not isinstance(business_id, str) or not business_id.strip():
        raise ParadosisError("BUSINESS_ID_REQUIRED")
    try:
        ctx = sanpedro_resolve(business_id.strip(), registry_path)
    except SanPedroError as exc:
        raise ParadosisError(f"TENANT_RESOLVE_FAILED:{exc}") from exc
    head = repo_head(repo_root)
    modules = _select_modules(objective, allowed_scope)
    return MissionPacket(
        mission_id=mission_id.strip(),
        repo=repo,
        branch=branch or repo_branch(repo_root),
        current_head=head,
        business_id=ctx.business_id,
        brand_id=(brand_id or ctx.business_id).strip(),
        objective=objective.strip(),
        allowed_scope=tuple(allowed_scope),
        forbidden_scope=tuple(forbidden_scope),
        relevant_modules=modules,
        canonical_context_refs=_context_refs_for(modules),
        security_boundaries=DEFAULT_SECURITY_BOUNDARIES,
        production_boundary=DEFAULT_PRODUCTION_BOUNDARY,
        test_requirements=DEFAULT_TEST_REQUIREMENTS,
        write_permissions=tuple(write_permissions),
        current_known_state=current_known_state,
    )


def bind_tenant(
    packet: MissionPacket,
    claimed_business_id: str | None,
    claimed_brand_id: str | None = None,
) -> MissionPacket:
    """Validate prompt/operator tenant claims against the bound packet.

    Any other business/brand appearing in a prompt does NOT rebind the
    packet: it fails closed. Returns the packet unchanged on match, so
    agents keep one shared instance.
    """
    if claimed_business_id is not None and claimed_business_id != packet.business_id:
        raise TenantBindingError(
            f"TENANT_MISMATCH:business_id:{claimed_business_id}"
        )
    if claimed_brand_id is not None and claimed_brand_id != packet.brand_id:
        raise TenantBindingError(
            f"TENANT_MISMATCH:brand_id:{claimed_brand_id}"
        )
    return packet


# ---------------------------------------------------------------------------
# Stale context protection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PacketFreshness:
    status: str  # FRESH | STALE
    packet_head: str
    current_head: str
    changed_files: tuple[str, ...]


def check_packet_freshness(
    packet: MissionPacket, repo_root: Path
) -> PacketFreshness:
    """Compare the packet's sealed HEAD against current HEAD.

    Reports STALE with the files that changed; it does not cancel the
    mission -- the caller refreshes relevant context and continues.
    """
    current = repo_head(repo_root)
    if current == packet.current_head:
        return PacketFreshness(
            status="FRESH", packet_head=packet.current_head,
            current_head=current, changed_files=(),
        )
    changed = _git(repo_root, "diff", "--name-only", packet.current_head, current)
    files = tuple(f for f in changed.splitlines() if f.strip())
    return PacketFreshness(
        status="STALE", packet_head=packet.current_head,
        current_head=current, changed_files=files,
    )


def refresh_packet(packet: MissionPacket, repo_root: Path) -> MissionPacket:
    """Rebuild the packet with identical parameters at the current HEAD."""
    return MissionPacket(
        mission_id=packet.mission_id,
        repo=packet.repo,
        branch=repo_branch(repo_root),
        current_head=repo_head(repo_root),
        business_id=packet.business_id,
        brand_id=packet.brand_id,
        objective=packet.objective,
        allowed_scope=packet.allowed_scope,
        forbidden_scope=packet.forbidden_scope,
        relevant_modules=packet.relevant_modules,
        canonical_context_refs=packet.canonical_context_refs,
        security_boundaries=packet.security_boundaries,
        production_boundary=packet.production_boundary,
        test_requirements=packet.test_requirements,
        write_permissions=packet.write_permissions,
        current_known_state=packet.current_known_state,
    )


def packet_summary(packet: MissionPacket) -> str:
    """Compact rendering for agent prompts (no secrets, no PII)."""
    lines = [
        f"mission_id: {packet.mission_id}",
        f"repo: {packet.repo} branch: {packet.branch} head: {packet.current_head[:12]}",
        f"tenant: business_id={packet.business_id} brand_id={packet.brand_id}",
        f"objective: {packet.objective}",
        f"allowed_scope: {', '.join(packet.allowed_scope) or '-'}",
        f"forbidden_scope: {', '.join(packet.forbidden_scope) or '-'}",
        f"relevant_modules: {', '.join(packet.relevant_modules)}",
        f"context_refs: {', '.join(packet.canonical_context_refs)}",
        f"production_boundary: {packet.production_boundary}",
        f"write_permissions: {', '.join(f'{k}={v}' for k, v in packet.write_permissions) or 'none'}",
        f"known_state: {packet.current_known_state or '-'}",
    ]
    return "\n".join(lines)
