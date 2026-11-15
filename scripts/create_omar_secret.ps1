# Generates a cryptographically secure Omar API key and sends it to Fly without printing the secret.
# Requires: authenticated flyctl and an existing app named omar-core.

$ErrorActionPreference = "Stop"

$app = "omar-core"

$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$secret = [Convert]::ToBase64String($bytes)

try {
    $payload = "OMAR_API_KEY=$secret"
    $payload | flyctl secrets import -a $app
    if ($LASTEXITCODE -ne 0) {
        throw "flyctl secrets import failed with exit code $LASTEXITCODE"
    }

    flyctl secrets list -a $app
    if ($LASTEXITCODE -ne 0) {
        throw "flyctl secrets list failed with exit code $LASTEXITCODE"
    }

    Write-Host "OMAR_API_KEY created in Fly for $app. Secret value was not printed."
}
finally {
    $secret = $null
    $bytes = $null
}
