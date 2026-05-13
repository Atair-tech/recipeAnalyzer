$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$keyPath = Join-Path $env:USERPROFILE ".tauri\recipe-analyzer-updater.key"
$passwordPath = Join-Path $env:USERPROFILE ".tauri\recipe-analyzer-updater.key.password"

if (-not (Test-Path $keyPath)) {
    throw "Updater signing private key not found: $keyPath"
}
if (-not (Test-Path $passwordPath)) {
    throw "Updater signing private key password not found: $passwordPath"
}

$env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content -Raw -Path $keyPath).Trim()
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = (Get-Content -Raw -Path $passwordPath).Trim()

npm run sidecar:build
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

npm run tauri:build
exit $LASTEXITCODE
