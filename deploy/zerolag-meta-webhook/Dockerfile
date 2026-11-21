# ZeroLag Meta Lead Ads webhook receiver — isolated Fly.io service.
#
# TENANT ISOLATION: this app serves ONLY the ZeroLag Lead Ads webhook
# receiver (zion_core.meta_leadgen, business_id "zerolag"). Do NOT mount
# other tenants' receivers here (Los Duros, Zmart, SCAN), and do NOT reuse
# omar-core, zmart-intake, or los-duros-ig-webhook. The Los Duros receiver
# pattern is reused by IMPORT only; its Instagram path is never touched.
#
# ONE-INSTANCE CONSTRAINT: dedupe is SQLite-backed at /data/leadgen.db.
# min_machines_running = 1 + auto_stop_machines = "off" pins one instance
# so the retry sweep and the dedupe store stay consistent. Do NOT scale
# this app horizontally until shared dedupe exists.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Minimal runtime surface: the receiver modules and BIBLIA (read-only).
COPY zion_core/ /app/zion_core/
COPY zmart360/ /app/zmart360/

EXPOSE 8080

# Reads ZEROLAG_WEBHOOK_VERIFY_TOKEN, META_APP_SECRET, META_PAGE_TOKEN,
# N8N_META_LEADS_URL from the runtime environment (fly secrets).
# Fails fast if any is missing; never prints values.
CMD ["python3", "-m", "zion_core.zerolag_leadgen_main"]
