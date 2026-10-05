"""SAN PEDRO registry resolver for ZION CORE."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SANPEDRO_KEYS = ROOT / "zmart360" / "san_pedro_registry.json"
DEFAULT_REGISTRY = SANPEDRO_KEYS  # compatibility alias

# Legacy business IDs that are CONTRACTUAL outside ZION and therefore cannot
# be renamed, mapped to the one canonical ZION identity. Example: Omar Core's
# brain/BUSINESS-REGISTRY.json (active on main) and its router/tests use
# "zerolag", while ZION's canonical registry identity is "zero-lag-wifi".
# The alias is applied once at ingress inside sanpedro_resolve, and only when
# the registry does not define the id explicitly (an explicit registry entry
# always wins, so no tenant can be silently merged). Every downstream
# artifact (BusinessContext, MissionPacket, BIBLIA retrieval) carries only
# the canonical identity, so tenant isolation and fail-closed mismatch
# checks (e.g. paradosis.bind_tenant) keep working on one identity.
BUSINESS_ID_ALIASES: dict[str, str] = {
    "zerolag": "zero-lag-wifi",
}


class SanPedroError(RuntimeError):
    pass


@dataclass(frozen=True)
class BusinessContext:
    business_id: str
    display_name: str
    isolation_key: str
    context_refs: tuple[str, ...]


def sanpedro_resolve(business_id: str, path: Path | None = None) -> BusinessContext:
    if not isinstance(business_id,str) or not business_id.strip() or business_id != business_id.strip():
        raise SanPedroError("BUSINESS_ID_REQUIRED")
    registry = json.loads((path or DEFAULT_REGISTRY).read_text(encoding="utf-8"))
    businesses = registry.get("businesses")
    if not isinstance(businesses, dict):
        raise SanPedroError("INVALID_REGISTRY")
    # An explicit registry entry always wins: the alias only applies when the
    # registry does not define the id, so a registered tenant can never be
    # silently merged into another tenant's context.
    canonical_id = business_id
    if business_id not in businesses:
        canonical_id = BUSINESS_ID_ALIASES.get(business_id, business_id)
    entry = businesses.get(canonical_id)
    if entry is None:
        raise SanPedroError("BUSINESS_NOT_REGISTERED")
    if entry.get("enabled") is not True:
        raise SanPedroError("BUSINESS_DISABLED")
    refs = entry.get("context_refs")
    if not isinstance(refs, list) or not refs or not all(
        isinstance(x,str) and x.strip() and x == x.strip() for x in refs
    ):
        raise SanPedroError("BUSINESS_CONTEXT_MISSING")
    if len(set(refs)) != len(refs):
        raise SanPedroError("BUSINESS_CONTEXT_DUPLICATE")
    isolation_key = entry.get("isolation_key")
    if (not isinstance(isolation_key,str) or not isolation_key.strip()
            or isolation_key != isolation_key.strip()):
        raise SanPedroError("ISOLATION_KEY_MISSING")
    return BusinessContext(
        business_id=canonical_id,
        display_name=str(entry.get("display_name") or canonical_id),
        isolation_key=isolation_key,
        context_refs=tuple(refs),
    )



def sanpedro_business_ids(path: Path | None = None) -> tuple[str, ...]:
    """Return canonical registered business IDs for isolation-aware parsing."""
    registry=json.loads((path or DEFAULT_REGISTRY).read_text(encoding="utf-8"))
    businesses=registry.get("businesses")
    if not isinstance(businesses,dict):
        raise SanPedroError("INVALID_REGISTRY")
    return tuple(
        business_id for business_id,entry in businesses.items()
        if isinstance(business_id,str) and business_id
        and isinstance(entry,dict) and entry.get("enabled") is True
    )

RegistryError = SanPedroError  # compatibility alias

def resolve_business(business_id: str, path: Path | None = None) -> BusinessContext:
    """Compatibility alias for SANPEDRO context resolution."""
    return sanpedro_resolve(business_id, path)
