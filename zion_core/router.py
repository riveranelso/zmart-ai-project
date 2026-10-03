"""SAN GABRIEL deterministic mission router.

This module intentionally performs routing only. It does not execute tools,
grant permissions, deploy code, or mutate canonical knowledge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "zmart360"

_ALLOWED_RISK = {"low", "medium", "high", "critical"}
_REQUIRED = ("mission_id", "intent", "requested_by", "scope")
_HOST_RE = re.compile(r"^[A-Z]+\.HOST-\d{2}$")


class MissionValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DispatchDecision:
    mission_id: str
    action: str
    reason: str
    command: str | None = None
    host: str | None = None
    angel_prefix: str | None = None
    human_review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_dispatch_routes(path: Path | None = None) -> dict[str, tuple[str, str]]:
    """Parse the deliberately simple route registry without third-party deps."""
    path = path or CONFIG_DIR / "dispatch_routes.yaml"
    routes: dict[str, tuple[str, str]] = {}
    current: dict[str, str] = {}
    in_routes = False

    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped == "routes:":
            in_routes = True
            continue
        if in_routes and stripped == "fallback:":
            break
        if not in_routes or not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- intent:"):
            if current:
                _store_route(routes, current)
            current = {"intent": str(_scalar(stripped.split(":", 1)[1]))}
        elif current and ":" in stripped:
            key, value = stripped.split(":", 1)
            if key in {"command", "host"}:
                current[key] = str(_scalar(value))

    if current:
        _store_route(routes, current)
    return routes


def _store_route(routes: dict[str, tuple[str, str]], route: dict[str, str]) -> None:
    missing = {"intent", "command", "host"} - route.keys()
    if missing:
        raise RuntimeError(f"Invalid dispatch route, missing: {sorted(missing)}")
    intent, command, host = route["intent"], route["command"], route["host"]
    if intent in routes:
        raise RuntimeError(f"Duplicate dispatch intent: {intent}")
    if not _HOST_RE.match(host) or not host.startswith(command + "."):
        raise RuntimeError(f"Invalid command/host pair: {command} -> {host}")
    routes[intent] = (command, host)


def validate_mission(mission: dict[str, Any]) -> None:
    if not isinstance(mission, dict):
        raise MissionValidationError("mission must be an object")

    missing = [key for key in _REQUIRED if not mission.get(key)]
    if missing:
        raise MissionValidationError(f"missing required fields: {', '.join(missing)}")

    risk = mission.get("risk_level", "low")
    if risk not in _ALLOWED_RISK:
        raise MissionValidationError("invalid risk_level")

    count = mission.get("angel_count_max", 1)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise MissionValidationError("angel_count_max must be an integer >= 1")

    for key in ("target_command", "target_host"):
        if key in mission and mission[key] is not None and not isinstance(mission[key], str):
            raise MissionValidationError(f"{key} must be a string or null")


def route_mission(
    mission: dict[str, Any],
    routes_path: Path | None = None,
) -> DispatchDecision:
    """Validate and route a mission without performing execution."""
    validate_mission(mission)
    routes = _load_dispatch_routes(routes_path)
    mission_id = str(mission["mission_id"])
    intent = str(mission["intent"])

    route = routes.get(intent)
    if route is None:
        return DispatchDecision(
            mission_id=mission_id,
            action="REQUIRE_HUMAN_REVIEW",
            reason="ROUTE_NOT_FOUND",
            human_review_required=True,
        )

    command, host = route

    requested_command = mission.get("target_command")
    requested_host = mission.get("target_host")
    if requested_command and requested_command != command:
        return DispatchDecision(
            mission_id=mission_id,
            action="REQUIRE_HUMAN_REVIEW",
            reason="TARGET_COMMAND_CONFLICT",
            human_review_required=True,
        )
    if requested_host and requested_host != host:
        return DispatchDecision(
            mission_id=mission_id,
            action="REQUIRE_HUMAN_REVIEW",
            reason="TARGET_HOST_CONFLICT",
            human_review_required=True,
        )

    if mission.get("human_approval_required", False):
        return DispatchDecision(
            mission_id=mission_id,
            action="REQUIRE_HUMAN_REVIEW",
            reason="HUMAN_APPROVAL_REQUIRED",
            command=command,
            host=host,
            human_review_required=True,
        )

    # High/critical risk is never auto-executed by this first router.
    if mission.get("risk_level", "low") in {"high", "critical"}:
        return DispatchDecision(
            mission_id=mission_id,
            action="REQUIRE_HUMAN_REVIEW",
            reason="RISK_GATE",
            command=command,
            host=host,
            human_review_required=True,
        )

    return DispatchDecision(
        mission_id=mission_id,
        action="DISPATCH",
        reason="ROUTE_MATCHED",
        command=command,
        host=host,
        angel_prefix=f"{host}.ANGEL-",
        human_review_required=False,
    )


def main() -> None:
    import sys

    payload = json.load(sys.stdin)
    print(json.dumps(route_mission(payload).to_dict(), indent=2))


if __name__ == "__main__":
    main()
