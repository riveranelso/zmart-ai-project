# zerolag-meta-webhook

Owned Meta Lead Ads ingestion for **ZeroLag WiFi** — receives Meta Instant
Form leads via Meta's native Lead Ads webhooks, bypassing GoHighLevel.
Tenant is fixed to `zerolag`; this app must never serve another tenant.

## What it does

```
Meta Instant Form (Zero Lag WiFi Page)
  -> POST /meta/webhooks/leadgen   (HMAC-SHA256 verified)
  -> translate leadgen payload     (leadgen_id, form_id, ad_id, ...)
  -> dedupe on leadgen_id          (SQLite, durable)
  -> fetch field_data via Graph API
  -> translate to ZeroLag schema
  -> forward to n8n                (retry w/ backoff, pending queue)
```

n8n then runs the existing ZeroLag path: normalize -> OMAR Verify Tenant
(fail-open, parallel) -> Gmail notification (1 per lead).

## Secrets (Fly secrets — names only, never values here)

| Secret | Purpose |
|---|---|
| `ZEROLAG_WEBHOOK_VERIFY_TOKEN` | Token Meta sends as `hub.verify_token` at subscription |
| `META_APP_SECRET` | Signs `X-Hub-Signature-256` (HMAC key) |
| `META_PAGE_TOKEN` | Page access token for Graph API lead fetch |
| `N8N_META_LEADS_URL` | n8n webhook URL receiving normalized leads |

Optional plain env: `ZEROLAG_PAGE_ID` (tenant allowlist), `LEAD_STORE_PATH`
(default `/data/leadgen.db`), `PORT` (default `8080`).

Set them with (values never printed by flyctl):
```
fly secrets set -a zerolag-meta-webhook ZEROLAG_WEBHOOK_VERIFY_TOKEN=...
fly secrets set -a zerolag-meta-webhook META_APP_SECRET=...
fly secrets set -a zerolag-meta-webhook META_PAGE_TOKEN=...
fly secrets set -a zerolag-meta-webhook N8N_META_LEADS_URL=...
```

Create the volume once:
```
fly volumes create zerolag_leadgen_data -a zerolag-meta-webhook -r iad -s 1
```

## Meta dashboard subscription (human action)

1. Create (or designate) the **ZeroLag Meta App** in the Meta dashboard.
2. Webhooks product -> add subscription:
   - Callback URL: `https://zerolag-meta-webhook.fly.dev/meta/webhooks/leadgen`
   - Verify token: the value stored in `ZEROLAG_WEBHOOK_VERIFY_TOKEN`
3. Subscribe the **Zero Lag WiFi Page** to the `leadgen` field on that
   callback URL. Keep the GoHighLevel subscription during canary.
4. Verify: Meta's dashboard "Test" sends the GET challenge; the app must
   answer 200 with the challenge echoed.

## No-cutover notice

Deploying this app changes **nothing** in production Meta. It receives
traffic only after a human subscribes the Page's `leadgen` field above.
GoHighLevel stays connected until the canary proves the owned path with
real leads. Campaigns are not touched by this service.

## Failure behavior

- Bad signature -> 401 (fail closed). Malformed payload -> 400.
- After signature verification: **always 200** (Meta's retry contract);
  unfinished fetch/forward work goes to the durable pending queue and is
  retried every 60s by the background sweep. No lead is lost on transient
  failure; duplicates are impossible (leadgen_id primary key).
- OMAR never blocks capture: verification happens downstream in n8n,
  fail-open.

## Logs

Structured JSON on `zion.meta_leadgen`. Correlation uses opaque truncated
hashes only. **Never logged:** secrets, tokens, signatures, raw bodies,
lead PII (names, phones, emails, addresses, answers), raw Meta ids.
