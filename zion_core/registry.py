"""SAN PEDRO registry resolver for ZION CORE."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SANPEDRO_KEYS = ROOT / "zmart360" / "san_pedro_registry.json"
DEFAULT_REGISTRY = SANPEDRO_KEYS  # compatibility alias


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
    entry = businesses.get(business_id)
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
        business_id=business_id,
        display_name=str(entry.get("display_name") or business_id),
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
