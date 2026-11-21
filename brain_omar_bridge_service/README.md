# Brain -> Omar Bridge Service

HTTP wrapper around `brain_omar_bridge/` (Python stdlib only — no
dependencies to install). Design note: `zmart360/BRAIN_OMAR_BRIDGE.md`.
Wiring spec: `zmart360/BRAIN_OMAR_BRIDGE_WIRING_SPEC.md`.

## Endpoints

- `POST /bridge/route` — body: ONE ESCALATION GATE item (JSON object,
  internal shape with the trusted `business_id`). Optional `?visual=1`.
  Requires caller authentication: header `X-Bridge-Key: <secret>` (see
  `BRIDGE_CALLER_KEY` below). Missing/wrong secret -> `401` and Omar is
  never called.
  - `200` -> BridgeResult JSON (`brain_business_id`, `omar_business_id`,
    `escalation_route`, `escalation_reason`, `visual`, `omar_route`).
  - Non-200 -> `{"ok": false, "error": "<ErrorTypeName>"}` only. Status
    map: caller auth 401, Brain contract/context errors 422, Omar
    config 500, Omar auth/rejected/response 502, Omar unreachable 503,
    bad JSON 400.
- `GET /health` — `{"ok": true, ...}`; never calls Omar, no auth needed.

## Configuration (environment only)

- `BRIDGE_CALLER_KEY` — the caller-authentication secret for
  `POST /bridge/route` (callers send it as the `X-Bridge-Key` header).
  Never hardcoded, never logged, never in any response. With it unset,
  the service boots and `/health` answers, but `/bridge/route` rejects
  every caller with 401 (fail closed).
- `OMAR_API_KEY` or `OMAR_API_KEY_FILE` — the Omar key. Never hardcoded,
  never logged, never in any response.
- `OMAR_CORE_BASE_URL` — default `https://omar-core.fly.dev`.
- `PORT` — default `8080`. `HOST` — default `0.0.0.0`.

With no Omar key set, the service boots and `/health` answers, while
`/bridge/route` fails closed with `OmarConfigError`.

## Run locally

```bash
BRIDGE_CALLER_KEY=<caller secret> \
OMAR_API_KEY_FILE=~/workspace/.secrets/omar-api-key \
    python3 -m brain_omar_bridge_service
```

## Tests

```bash
python3 -m pytest tests/test_brain_omar_bridge_service.py   # unit (fake transport)
OMAR_API_KEY_FILE=~/workspace/.secrets/omar-api-key \
    python3 -m brain_omar_bridge_service.shadow_e2e          # live shadow, synthetic data
```

## Deploy (Fly app `brain-omar-bridge`, region iad)

The Docker build context is the **repository root** (the image copies
both `brain_omar_bridge/` and `brain_omar_bridge_service/`). Deploy
from the repo root so the context is correct:

```bash
fly deploy -c brain_omar_bridge_service/fly.toml \
    --dockerfile brain_omar_bridge_service/Dockerfile
fly secrets set OMAR_API_KEY=<value> -a brain-omar-bridge   # value from the vault, never committed
fly secrets set BRIDGE_CALLER_KEY=<value> -a brain-omar-bridge   # caller secret, same rule
```

`shadow_e2e.py` ships inside the image; it is a test tool and is never
invoked by the service.
