# Brain → Omar Bridge — Design Note

Status: SERVICE BUILT + TESTED, N8N SHADOW WIRING LIVE (2026-11-20).
Fly deployment BLOCKED at app creation (see Activation log below).
Module: `brain_omar_bridge/` · Service: `brain_omar_bridge_service/` ·
Tests: `tests/test_brain_omar_bridge.py` (unit),
`tests/test_brain_omar_bridge_live.py` (live API, opt-in),
`tests/test_brain_omar_bridge_service.py` (service unit).

## Where the bridge sits

```
consumer message
      │
      ▼
n8n "NELSON AI | Zmart Brain v1"  ──►  ESCALATION GATE item (internal)
      │                                        │
      │  public webhook response               │  business_id present here,
      │  (business_id STRIPPED by              │  stripped from the response
      │   the RESPOND node)                    ▼
      │                              ┌───────────────────┐
      └─────────────────────────────►│  Brain→Omar bridge │ (this module)
                                     └─────────┬─────────┘
                                               │ POST /omar/route
                                               │ X-Omar-Key, {business_id, visual}
                                               ▼
                                     Omar Core (omar-core.fly.dev)
                                     canonical route per business
```

The bridge is a small client-side adapter, deliberately NOT a node inside
the n8n workflow and NOT part of Omar Core. It is the reusable pattern for
any future "system X result → Omar route" adapter: validate the producer's
contract, resolve the business identity through an explicit map, call Omar,
verify Omar's answer, and fail closed on any doubt.

## What payload the Brain produces (verified live 2026-11-20)

Checked against the live workflow via the read-only n8n API and the
redacted baseline snapshot (`~/workspace/zmart-n8n-audit/`). The live
workflow matches the snapshot's contract; the only diffs are a narrow
emergency-negation guard in the gate and prompt text — neither changes
the output shape.

The ESCALATION GATE item carries the STRUCTURED OUTPUT fields plus the
gate's deterministic derivation:

- `intent`, `channel`, `language`, `lead_status`, `priority`,
  `recommended_action`, `response`, `requires_human`, `reason`
- `escalation_route` ∈ {`routine`, `main_brain`, `human_review`}
- `escalation_reason` (deterministic string, e.g. `clear_low_risk`)
- `business_id`, `config_version` — stamped by PROFILE LOADER from
  trusted workflow configuration, NEVER from the caller payload or the
  model output.

The public webhook response is the same JSON **minus `business_id` and
`config_version`** (the RESPOND node strips them deliberately).

## How business_id is determined

PROFILE LOADER holds exactly one live profile today: trusted id `zmart`.
Omar Core's id for the same business is `zmart-consumer`. The bridge maps
explicitly (`BRAIN_TO_OMAR_BUSINESS_ID` in `brain_omar_bridge/bridge.py`):

| Brain trusted id | Omar business_id | Status |
|---|---|---|
| `zmart` | `zmart-consumer` | live Brain profile |
| `scan` | `scan` | identity map; no Brain profile yet |
| `zerolag` | `zerolag` | identity map; no Brain profile yet |
| `los-duros` | `los-duros` | identity map; no Brain profile yet |

Because the public response strips `business_id`, the bridge must be fed
the internal gate item (or a trusted side channel carrying the same
value). Fed the public response alone, it raises
`MissingBusinessContextError`. It never defaults to Zmart: a route for
the wrong business is worse than no route.

## How the bridge calls Omar

`POST {OMAR_CORE_BASE_URL}/omar/route` (default base
`https://omar-core.fly.dev`), header `X-Omar-Key: <key>`, JSON body
`{"business_id": <omar id>, "visual": <bool>}`. `visual` tells Omar the
work involves visual output; Omar echoes it as `visual_gate_required`
in the route. The key comes from `OMAR_API_KEY` or `OMAR_API_KEY_FILE`
(environment only — never hardcoded, never logged, never in errors).

A response counts as a route only if ALL hold: HTTP 200, body is JSON,
`ok` is `true`, `route` is an object, and `route.business_id` equals the
requested id. Verified Omar response shape (live, 2026-11-20):

```json
{"ok": true, "route": {"business_id": "zmart-consumer",
 "name": "Zmart Consumer Rights",
 "repository": "riveranelso/zmart-consumer-rights",
 "rules": ["brand/COMPLIANCE.md"], "asset_registry": "...",
 "brain_mode": "project_rules", "status": "active",
 "visual_gate_required": false, "notes": "...", "asset_status": null}}
```

## Fail-closed behavior

The bridge NEVER invents, caches, or falls back to a local route. Every
doubt raises a typed `BridgeError` and the caller surfaces the failure:

| Condition | Error | HTTP call made? |
|---|---|---|
| Brain payload missing a contract field | `BrainContractError` | no |
| `escalation_route` not in the known set | `BrainContractError` | no |
| No trusted `business_id` in payload | `MissingBusinessContextError` | no |
| Brain id with no Omar mapping | `UnknownBusinessError` | no |
| No key configured | `OmarConfigError` | no |
| Omar unreachable / timeout / DNS / TLS | `OmarUnreachableError` | attempted |
| Omar HTTP 400 (unknown business) | `OmarRejectedError` | yes |
| Omar HTTP 401/403 | `OmarAuthError` | yes |
| Omar HTTP other, non-JSON, `ok != true`, missing/mismatched route | `OmarResponseError` | yes |

The Brain's own escalation decision (`escalation_route` /
`escalation_reason`) is passed through unchanged in `BridgeResult`; the
bridge adds Omar's canonical route next to it and overrides nothing.

## Activation log — 2026-11-20 (owner full-go, "todo lo que haya que hacer")

Executed under Nelson's explicit full authorization, layer by layer,
each layer verified before the next.

### Layer 1 — service + tests (local / LIVE API) ✅

- HTTP service wrapper built: `brain_omar_bridge_service/` (stdlib
  `http.server` only). `POST /bridge/route` takes ONE gate item and
  returns the BridgeResult JSON; typed bridge errors map to non-200
  with ONLY the error type name (422 contract/context, 500 config,
  502 Omar auth/rejected/response, 503 unreachable, 400 bad JSON).
  `GET /health` never calls Omar. Key from env only.
- Tests: bridge unit 21/21; service unit 8/8 (valid item → 200 pairing;
  public-response shape → MissingBusinessContextError; missing field →
  BrainContractError; Omar 401 → OmarAuthError; health makes zero Omar
  calls; no key material in any response body).
- Live suite (opt-in) 5/5 against real Omar. (First combined run showed
  2 transient failures while Omar's machine cycled; isolated and full
  reruns pass 5/5.)
- Live shadow E2E through the wrapper (`shadow_e2e.py`, synthetic item,
  `business_id "zmart"`, `escalation_route "routine"`,
  `escalation_reason "clear_low_risk"`): HTTP 200, pairing
  zmart → zmart-consumer, Omar route returned with
  `repository riveranelso/zmart-consumer-rights`, `status active`.

### Layer 2 — Fly deployment ⛔ BLOCKED at app creation

- Deployment package ready: `brain_omar_bridge_service/Dockerfile` +
  `fly.toml` (app `brain-omar-bridge`, iad, internal port 8080,
  `/health` check). Build context is the repo root.
- App name `brain-omar-bridge` is free (GraphQL app lookup: NOT_FOUND).
- `createApp` via the `custom.flyio` API token returned
  **UNAUTHORIZED — "Not authorized to deploy this app."** The token
  Nelson issued can write to omar-core (secrets, machines — proven) but
  cannot create apps.
- flyctl v0.4.111 exists on this VM but holds **no access token**, and
  the connector credential is surrogate-only (it cannot authenticate
  flyctl or a Docker push). This VM also has no Docker daemon, and
  `fly deploy` from this VM was already depot-TLS-blocked historically.
- Therefore: app not created, secret not set on it, nothing deployed,
  `brain-omar-bridge.fly.dev` does not resolve (verified). No workaround
  was improvised around the authorization boundary.
- **Single remaining owner step:** create the app in Nelson's own Fly
  session (`fly apps create brain-omar-bridge` or the Fly dashboard —
  his PC's flyctl login works, as used for the Los Duros secret), or
  issue a Fly token with app-create/deploy rights. After that, from
  here: set `OMAR_API_KEY` on the app via API, deploy the package,
  verify deployed `/health` + synthetic POST, in that order.

### Layer 3 — n8n wiring ✅ LIVE (shadow mode)

- Write route determined: the stored n8n Public REST API key carries
  workflow-update scope (probe: PUT to a nonexistent id passed auth and
  body validation, returning 404 — a scope failure would have been 403;
  nothing was modified by the probe).
- Implemented exactly per `zmart360/BRAIN_OMAR_BRIDGE_WIRING_SPEC.md`:
  two nodes added (`OMAR BRIDGE — Shadow POST` httpRequest 4.2,
  `onError=continueRegularOutput`, 5 s timeout; `OMAR BRIDGE — Shadow
  Log` noOp) and one appended fan-out destination on ESCALATION GATE.
  Importable JSON: `brain_omar_bridge_service/n8n_shadow_branch_nodes.json`.
- Verified against the live workflow after the write (fresh GET +
  diff): workflow still **active**, 23 nodes, **all 21 pre-existing
  nodes deep-equal**, RESPOND — Brain Output byte-identical, every
  pre-existing connection unchanged except the single appended fan-out,
  `settings`/`name` unchanged. The public RESPOND path is provably
  untouched at the definition layer.

### Layer 4 — end-to-end verification (partial, honestly bounded)

- (a) Wired branch → bridge → Omar: **not yet provable in production** —
  the bridge service is not deployed (Layer 2), so Shadow POST calls
  currently fail-swallow by design. The same path IS proven locally
  end-to-end against live Omar (Layer 1 shadow E2E).
- (b) Brain public behavior unchanged: proven at the definition layer
  (deep-equal diff above; fan-out cannot alter the item RESPOND
  receives). Execution-layer proof was not obtainable from here: the
  production webhook requires its header-auth credential (held in n8n's
  credential store), the manual test trigger needs the UI session, and
  the executions API returns an empty list for this workflow.

### Mode: shadow, not yet "active"

The branch runs in shadow/log-only mode. Flipping to "active" (a
downstream consumer attaching Omar's route alongside the Brain result)
has no consumer to attach to yet and is meaningless until the service
is deployed; it remains a separate owner-visible step after Layer 2
completes. Nothing about consumer-facing Brain answers changes in
either mode.

### Remaining owner decisions / steps

1. Create Fly app `brain-omar-bridge` (owner session) or grant the API
   token app-create rights → unblocks deploy, secret placement, and
   deployed-service verification.
2. After deployment: approve flipping the branch from shadow to active
   consumption, and name the downstream consumer of the pairing.
3. Optional: run one manual test from the n8n UI (fictitious test input
   node) to capture an execution-layer record of the branch firing.

## What production activation still requires (NOT done here)

1. A wiring decision by Nelson: where the bridge runs (a small service,
   or a caller-side adapter next to the Brain's consumer) and who feeds
   it the internal gate item, since the public response strips
   `business_id` by design.
2. A production home for the Omar key (env/secret on that runtime),
   sourced from the same vault value — never copied into the repo.
3. An explicit go/no-go on routing live Brain results through Omar.
   Until then, no live traffic changes: the n8n workflow is untouched
   and nothing calls the bridge in production.

> The three items above are the pre-authorization record. They were
> superseded by the owner's 2026-11-20 full-go and the Activation log
> above: the wiring decision was taken (small Fly service + n8n shadow
> branch), the workflow HAS been wired in shadow mode, and the key's
> production home is the bridge app's Fly secret (pending Layer 2).

## REVISIÓN ADVERSARIAL #1 — ciclo constructor/revisor (2026-11-20)
Revisor separado (rol destructor), suite existente 29/29 verde antes de empezar. Pruebas: tests/test_brain_omar_bridge_adversarial.py — 12 escritas, 12 FALLAN (bugs confirmados), sin tocar bridge.py ni service.py:
1. service.py — POST /bridge/route SIN autenticación del llamante (200 sin key; usa la key Omar del bridge). fly.toml = http_service público → BLOQUEA EL DEPLOY hasta corregirlo.
2. service.py:127 — Content-Length: -1 clava un hilo indefinidamente (DoS).
3. service.py:127 — Content-Length < -1 → ValueError, conexión caída sin JSON.
4. service.py:129 — JSON anidado profundo → RecursionError no capturado, conexión caída (debía ser 400).
5. service.py:102/114 — método no soportado (PUT) → 501 HTML de stdlib, rompe el contrato de error JSON.
6. bridge.py:166 — OMAR_API_KEY_FILE inexistente/directorio → error crudo, no OmarConfigError; mata el proceso antes de /health.
7. bridge.py:225 — escalation_route no hasheable (lista/dict) → TypeError crudo, no BrainContractError.
8. bridge.py:222 — payload no-Mapping → AttributeError pese a docstring "BridgeError on any doubt".
9. bridge.py:172 — OmarClient.route() business_id no hasheable → TypeError, no UnknownBusinessError.
10. CONFLICTO DE CONTRATO: business_id desconocido devuelve 422 (README del servicio lo documenta como decisión deliberada) vs contrato entregado que exige 400 — lo dirime Nelson.
HIPÓTESIS (sin prueba): strip silencioso de espacios en business_id; campos del GATE vacíos/tipo incorrecto pasan; sin validación de Content-Type; espacios en OMAR_API_KEY de entorno sin strip.
LIMPIO: mapeo fail-closed, higiene del secreto (no aparece en logs/errores/respuestas), verificación de respuesta de Omar, cap 256 KB, resiliencia global del proceso.
ESTADO: correcciones PENDIENTES (paso 4 del ciclo) — nada corregido, nada commiteado.

## CORRECCIÓN DE LA REVISIÓN ADVERSARIAL #1 — 2026-11-21 (rama fix/zion-omar-integration-20261121)
Hallazgos 1–9 CORREGIDOS, cada uno confirmado antes por su prueba adversarial y verde después:
1. Autenticación del llamante en el servicio: `POST /bridge/route` exige header `X-Bridge-Key` comparado en tiempo constante contra el secreto de la variable de entorno `BRIDGE_CALLER_KEY` (documentada en el README del servicio; nunca hardcodeado). Sin secreto configurado, toda llamada → 401 (fail closed) y Omar nunca es llamado. `/health` sigue sin auth.
2/3. Content-Length negativo → 400 `InvalidContentLength` JSON (antes: hilo clavado con -1, conexión caída con <-1).
4. JSON anidado profundo → 400 `InvalidJsonBody` (RecursionError capturado).
5. PUT/DELETE/PATCH/OPTIONS → 405 JSON `MethodNotAllowed` (antes: 501 HTML de stdlib).
6. `OMAR_API_KEY_FILE` ilegible (inexistente/directorio) → `OmarConfigError` (antes: OSError crudo que mataba el proceso).
7. `escalation_route` no hasheable (lista/dict) → `BrainContractError` (antes: TypeError).
8. Payload no-Mapping → `BrainContractError` (antes: AttributeError).
9. `OmarClient.route()` con business_id no-string → `UnknownBusinessError` (antes: TypeError).
10. PENDIENTE DE DECISIÓN DE NELSON (sin tocar): desconocido sigue devolviendo 422 por diseño del servicio vs 400 que exige el contrato entregado. Su prueba adversarial sigue fallando — y desde la corrección del #1 falla antes, en la capa de auth (la prueba no envía credencial de llamante y recibe 401).
Suite al cierre: bridge 21/21, servicio 10/10, adversarial 11/12 (solo #10 en rojo, por decisión pendiente).
NOTA DE CABLEADO: la rama shadow de n8n (`OMAR BRIDGE — Shadow POST`) no envía `X-Bridge-Key`; cuando el servicio corregido se despliegue, esa rama recibirá 401 hasta que se le configure el header con el secreto (paso de despliegue, no hecho aquí).
