# Omar Security Gate

Status: ACTIVE — REQUIRED BEFORE PRODUCTION TRAFFIC
Owner: Nelson Rivera

## Purpose
Security is part of the build, not a post-deploy checklist. Omar must fail closed when a required security control is missing.

## Implemented controls

### 1. Authentication
- Protected endpoints require the `X-Omar-Key` header.
- The expected secret comes only from the `OMAR_API_KEY` environment variable.
- Secrets are never stored in GitHub.
- Comparison is constant-time.
- If `OMAR_API_KEY` is missing, protected requests fail closed with HTTP 503.
- Wrong or missing keys return HTTP 401.

### 2. Input restrictions
- `business_id` is limited to 64 characters.
- Allowed characters: lowercase letters, digits, and hyphens.
- Unknown and inactive businesses fail closed through the router.
- No arbitrary repository path, URL, shell command, prompt, or tool name is accepted from the caller.

### 3. Rate limiting
- Protected requests have a conservative per-process limit.
- Default: 60 requests/minute/client.
- Override only with `OMAR_RATE_LIMIT_PER_MINUTE`.
- Multi-machine deployments require an edge/shared rate limiter before scale-out.

### 4. Browser exposure
- No CORS middleware is enabled.
- Swagger/OpenAPI/ReDoc are disabled in production runtime.
- Responses include anti-sniff, anti-frame, no-referrer, and no-store headers.

### 5. Logging / privacy
- Omar application code must never log API keys, request bodies, customer PII, contracts, quiz answers, or evidence payloads.
- Access logs may contain transport metadata such as IP, method, route, status, and timing; retention must be reviewed separately at the hosting layer.
- If future endpoints accept customer data, add explicit redaction before any application logging is introduced.

### 6. Secrets
- Production secret must be created outside GitHub, for example with Fly secrets.
- Never paste production secrets into source, commits, issues, prompts, screenshots, or chat transcripts.
- Rotate immediately if exposure is suspected.

## Required deployment order
1. Tests pass.
2. Create/confirm the new Omar app only.
3. Set `OMAR_API_KEY` as a platform secret.
4. Deploy Omar.
5. Verify public `/health`.
6. Verify protected route rejects requests without a key.
7. Verify protected route accepts the correct key.
8. Verify all registered businesses route correctly.
9. Connect one non-production caller first.
10. Run end-to-end validation.
11. Only then connect production workflows and restore traffic.

## Stop conditions
Do not proceed with production traffic if:
- the secret is missing,
- authentication can be bypassed,
- an unknown business routes successfully,
- logs expose secrets or PII,
- ZeroLag asset conflict would cause an invented/substituted logo,
- a production change would affect a different app or brand.

## Existing Zmart principle
Where Zmart systems already use authenticated webhook entry (for example, a required secret header), keep that fail-closed pattern. Omar does not weaken downstream security; each downstream system retains its own authentication and authorization controls.
