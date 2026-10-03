# Create Omar API Secret

This helper creates a cryptographically secure `OMAR_API_KEY` locally and sends it directly to Fly.

It intentionally does **not** print or commit the secret.

## PowerShell

Run from the repository root after `flyctl auth whoami` confirms the correct account and after the `omar-core` app exists:

```powershell
./scripts/create_omar_secret.ps1
```

The script uses `flyctl secrets import` and then lists secret names only for verification.

Do not copy the secret into GitHub, chat, screenshots, logs, or `fly.toml`.
