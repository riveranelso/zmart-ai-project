"""Deterministic Omar business router.

This module does not call business systems or mutate production. It resolves a
trusted business_id to the repository/rules that an execution layer must load.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RouteError(ValueError):
    pass


@dataclass(frozen=True)
class RoutePlan:
    business_id: str
    name: str
    repository: str
    rules: tuple[str, ...]
    asset_registry: str | None
    brain_mode: str
    status: str
    visual_gate_required: bool
    notes: str | None = None
    asset_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "name": self.name,
            "repository": self.repository,
            "rules": list(self.rules),
            "asset_registry": self.asset_registry,
            "brain_mode": self.brain_mode,
            "status": self.status,
            "visual_gate_required": self.visual_gate_required,
            "notes": self.notes,
            "asset_status": self.asset_status,
        }


class OmarRouter:
    def __init__(self, registry_path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[1]
        self.registry_path = Path(registry_path) if registry_path else root / "brain" / "BUSINESS-REGISTRY.json"
        self.registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self._businesses = {b["business_id"]: b for b in self.registry["businesses"]}

    def route(self, business_id: str, *, visual: bool = False) -> RoutePlan:
        key = (business_id or "").strip().lower()
        if not key:
            raise RouteError("business_id is required")
        business = self._businesses.get(key)
        if business is None:
            raise RouteError(f"unknown business_id: {key}")
        if business.get("status") != "active":
            raise RouteError(f"business_id is not active: {key}")
        return RoutePlan(
            business_id=key,
            name=business["name"],
            repository=business["repository"],
            rules=tuple(business.get("rules", [])),
            asset_registry=business.get("asset_registry"),
            brain_mode=business.get("brain_mode", "project_rules"),
            status=business["status"],
            visual_gate_required=bool(visual),
            notes=business.get("notes"),
            asset_status=business.get("asset_status"),
        )
