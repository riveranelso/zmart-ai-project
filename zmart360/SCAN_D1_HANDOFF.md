# SCAN D1 -> ZION handoff

Authoritative production source:
- Cloudflare D1: `scanwater-fl`
- Table: `fl_zip_water_systems`
- Worker binding: `DB`

## Read-only snapshot

Run from the authenticated Wrangler environment:

```powershell
npx.cmd wrangler d1 execute scanwater-fl --remote --command "SELECT zip, status, pwsid, city, candidates_json FROM fl_zip_water_systems ORDER BY zip;" --json > scan_zip_snapshot.json
```

This command is intentionally SELECT-only. It does not update D1 or deploy the Worker.

## Baseline verification

Before processing, verify the live distribution rather than trusting an old export:

```powershell
npx.cmd wrangler d1 execute scanwater-fl --remote --command "SELECT status, COUNT(*) AS count FROM fl_zip_water_systems GROUP BY status ORDER BY status;" --json
```

Also verify total ZIPs:

```powershell
npx.cmd wrangler d1 execute scanwater-fl --remote --command "SELECT COUNT(*) AS total FROM fl_zip_water_systems;" --json
```

## ZION ingestion rule

Only rows whose live status is `needs_more_location` enter the new resolution batch.
Existing `resolved` rows are preserved.
Duplicate ZIPs with conflicting statuses fail closed.
A ZIP cannot become `RESOLVED` without a valid PWSID and evidence.
Ambiguous ZIPs remain `NEEDS_MORE_LOCATION`; never guess a PWSID.

No UPDATE/INSERT/DELETE is authorized by this handoff.
