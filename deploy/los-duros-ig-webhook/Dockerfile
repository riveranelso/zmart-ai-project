# Los Duros Instagram webhook receiver — isolated Fly.io service.
#
# TENANT ISOLATION: this app serves ONLY the Los Duros Instagram webhook
# receiver (zion_core.meta_webhook, business_id los-duros). Do NOT mount
# other tenants' receivers here, and do NOT reuse omar-core or zmart-intake.
#
# ONE-INSTANCE CONSTRAINT: dedupe is process-local (in-memory seen-set), so
# this app must run exactly ONE machine until shared dedupe exists.
# min_machines_running = 1 + auto_stop_machines = "off" pins one instance.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Minimal runtime surface: the receiver, the tenant registry, and BIBLIA.
COPY zion_core/ /app/zion_core/
COPY zmart360/ /app/zmart360/

EXPOSE 8080

# Reads LOS_DUROS_IG_WEBHOOK_VERIFY_TOKEN, META_APP_SECRET,
# LOS_DUROS_IG_ACCOUNT_ID from the runtime environment (fly secrets).
# Fails fast if any is missing; never prints values.
CMD ["python3", "-m", "zion_core.meta_webhook"]
