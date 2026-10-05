# Los Duros Instagram webhook receiver — deploy notes

Isolated Fly.io service for the Los Duros Instagram webhook receiver
(`zion_core.meta_webhook`, branch `zmart360/omar-core-v1`).

- Callback path: `POST/GET /meta/webhooks/instagram`
- Health: `GET /health` → `200 ok`
- Tenant: **los-duros only** — never mount another tenant here.
- Instances: **exactly 1** (dedupe is process-local; do not scale out
  until shared dedupe exists).

## Required secrets (names only — values never go in git)

Set with `fly secrets set` (run from this directory):

- `LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN` — strong random token; the SAME
  value must be entered in the Meta app dashboard Verify Token field.
  Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `META_APP_SECRET` — App Secret of the Meta "Los Duros" app
  (dashboard: Configuración → Básica → Secreto de la app).
- `LOS_DUROS_IG_ACCOUNT_ID` — numeric professional Instagram account ID
  of @losdurosconlosduros (the `entry.id` Meta sends in webhooks).

## Deploy

All commands run from the **repo root** (`~/workspace/zmart-ai-project`),
so the Docker build context includes `zion_core/` and `zmart360/`:

```sh
fly apps create los-duros-ig-webhook   # once; skip if it exists
fly secrets set -a los-duros-ig-webhook \
  LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN=... \
  META_APP_SECRET=... \
  LOS_DUROS_IG_ACCOUNT_ID=...
fly deploy --config deploy/los-duros-ig-webhook/fly.toml
```

Production callback URL after deploy:

    https://los-duros-ig-webhook.fly.dev/meta/webhooks/instagram

(If the app name is taken, the actual `*.fly.dev` hostname is shown by
`fly apps create` / `fly status`.)

## Smoke test (after deploy)

```sh
BASE=https://los-duros-ig-webhook.fly.dev
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/health"   # expect 200
# wrong verify token -> expect 403
curl -s -o /dev/null -w "%{http_code}\n" \
  "$BASE/meta/webhooks/instagram?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=abc"
```

Full signed-POST smoke tests live in
`tests/test_zion_meta_webhook.py::HttpAdapterSmokeTests`.

## Rollback

- `fly deploy` keeps prior releases: `fly releases` then
  `fly deploy --image <previous-image>` to roll back.
- To fully remove: `fly apps destroy los-duros-ig-webhook`
  (no other service depends on this app).
