"""SAN PEDRO registry resolver for ZION CORE."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "zmart360" / "san_pedro_registry.json"


class RegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class BusinessContext:
    business_id: str
    display_name: str
    isolation_key: str
    context_refs: tuple[str, ...]


def resolve_business(business_id: str, path: Path | None = None) -> BusinessContext:
    if not business_id or not isinstance(business_id, str):
        raise RegistryError("BUSINESS_ID_REQUIRED")
    registry = json.loads((path or DEFAULT_REGISTRY).read_text(encoding="utf-8"))
    businesses = registry.get("businesses")
    if not isinstance(businesses, dict):
        raise RegistryError("INVALID_REGISTRY")
    entry = businesses.get(business_id)
    if entry is None:
        raise RegistryError("BUSINESS_NOT_REGISTERED")
    if entry.get("enabled") is not True:
        raise RegistryError("BUSINESS_DISABLED")
    refs = entry.get("context_refs")
    if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x for x in refs):
        raise RegistryError("BUSINESS_CONTEXT_MISSING")
    isolation_key = entry.get("isolation_key")
    if not isinstance(isolation_key, str) or not isolation_key:
        raise RegistryError("ISOLATION_KEY_MISSING")
    return BusinessContext(
        business_id=business_id,
        display_name=str(entry.get("display_name") or business_id),
        isolation_key=isolation_key,
        context_refs=tuple(refs),
    )
