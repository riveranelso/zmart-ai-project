"""Omar Core deterministic business router.

This module performs routing only. It does not call external services,
deploy code, mutate production systems, or merge brand contexts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

BRAIN_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BRAIN_DIR / "BUSINESS-REGISTRY.json"


class OmarRoutingError(ValueError):
    """Fail-closed routing error."""


@dataclass(frozen=True)
class Route:
    business_id: str
    name: str
    repository: str
    rules: tuple[str, ...]
    asset_registry: str
    notes: str | None = None
    asset_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "name": self.name,
            "repository": self.repository,
            "rules": list(self.rules),
            "asset_registry": self.asset_registry,
            "notes": self.notes,
            "asset_status": self.asset_status,
        }


def load_registry(path: Path = REGISTRY_PATH) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("status") != "ACTIVE":
        raise OmarRoutingError("Omar business registry is not ACTIVE")
    return data


def resolve_business(business_id: str, registry: Mapping[str, Any] | None = None) -> Route:
    if not isinstance(business_id, str) or not business_id.strip():
        raise OmarRoutingError("business_id is required")

    normalized = business_id.strip().lower()
    data = registry or load_registry()

    for item in data.get("businesses", []):
        if item.get("business_id") == normalized:
            if item.get("status") != "active":
                raise OmarRoutingError(f"business_id is not active: {normalized}")
            return Route(
                business_id=normalized,
                name=item["name"],
                repository=item["repository"],
                rules=tuple(item.get("rules", [])),
                asset_registry=item["asset_registry"],
                notes=item.get("notes"),
                asset_status=item.get("asset_status"),
            )

    raise OmarRoutingError(f"unknown business_id: {normalized}")


def route_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic routing plan. No side effects."""
    if not isinstance(payload, Mapping):
        raise OmarRoutingError("payload must be an object")

    route = resolve_business(payload.get("business_id"))
    plan = route.as_dict()
    plan["router"] = "omar"
    plan["routing_status"] = "ROUTED"
    plan["production_mutation_authorized"] = False
    return plan
