# Los Duros Instagram webhook receiver — deploy notes

Isolated Fly.io service for the Los Duros Instagram webhook receiver
(`zion_core.meta_webhook`, branch `zmart360/omar-core-v1`).

- Callback path: `POST/GET /meta/webhooks/instagram`
- Health: `GET /health` → `200 ok`
- Tenant: **los-duros only** — never mount another tenant here.
- Instances: **exactly 1** (dedupe is process-local L1 + per-machine
  SQLite L2 on the volume; a Fly volume attaches to one machine only —
  do not scale out).

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

## Durable approval storage — STAGED, NOT YET APPLIED

The approval queue (`zion_core/approval_queue.py`) now persists to a
single SQLite database (stdlib `sqlite3`, WAL mode) with atomic
enqueue: one transaction establishes event-fingerprint uniqueness and
creates the approval record, so a retried delivery — even after a
machine restart — can never create a duplicate approval, and human
decisions (APPROVED/EDITED/REJECTED) survive restarts.

The database file MUST live on a Fly persistent volume; without one it
is as ephemeral as the rest of the machine disk. The volume and mount
are **documented here but deliberately NOT applied** to `fly.toml` yet:
adding `[mounts]` before the volume exists would make the next deploy
fail, so the branch stays in a safe deploy state until the volume is
created.

### Steps (run in this order, each needs explicit authorization)

1. Create the volume (once, same region as the app):

   ```sh
   fly volumes create losduros_approvals --region iad --size 1 -a los-duros-ig-webhook
   ```

2. Add the mount to `deploy/los-duros-ig-webhook/fly.toml`:

   ```toml
   [mounts]
     source = "losduros_approvals"
     destination = "/data"
   ```

3. Point the receiver at the durable path:

   ```sh
   fly secrets set -a los-duros-ig-webhook LOS_DUROS_APPROVAL_STORE=/data/approvals.db
   ```

4. Deploy (mount changes require a deploy), then verify:
   health → GET verification → signed POST → duplicate POST reuses the
   approval → restart the machine → redelivery still reuses the approval
   and any prior human decision is intact.

Without `LOS_DUROS_APPROVAL_STORE` set, webhook behavior is unchanged
(drafts are created in memory and discarded; nothing is published).

### Backup strategy

- **Primary (off-volume, real disaster recovery): Fly volume snapshots.**
  Take them on a schedule (e.g. daily) and keep several generations.
  Restore = create a new volume from a snapshot and attach it. This is
  the only backup that survives volume loss.
- **Secondary (same-volume, operational convenience — NOT disaster
  recovery):** a periodic `VACUUM INTO '/data/backups/approvals-<date>.db'`
  copy. Useful for quick local restore of an accidentally corrupted file,
  but it dies with the volume, so it must never be the only backup.
- **Tertiary (portable, human-readable):** a periodic JSONL export of the
  `approvals` + `approval_history` tables, stored off the machine. Cheap
  insurance and the easiest path for future migrations.

### Restore

1. Stop the machine (single instance — no writes during restore).
2. Restore the volume from the latest snapshot (or copy a good
   `VACUUM INTO` backup over `/data/approvals.db`).
3. Start the machine; `ensure_ready()` validates the database and fails
   closed (no silent recreate) if it is corrupt.
4. Re-run the signed-POST + redelivery verification above.
