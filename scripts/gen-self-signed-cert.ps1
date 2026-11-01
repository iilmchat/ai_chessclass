# Self-signed TLS для локальной проверки edge-nginx (S-38).
# Production: Let's Encrypt/certbot или корпоративный сертификат — см. runbook.
param(
    [string]$OutDir = "deploy/certs",
    [string]$CommonName = "localhost",
    [int]$Days = 365,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$resolved = (Resolve-Path -LiteralPath ".").Path
$target = Join-Path $resolved $OutDir
New-Item -ItemType Directory -Force -Path $target | Out-Null

$cert = Join-Path $target "fullchain.pem"
$key = Join-Path $target "privkey.pem"
if ((Test-Path $cert) -and -not $Force) {
    throw "certificate exists: $cert (use -Force to overwrite)"
}

docker run --rm -v "${target}:/certs" alpine/openssl req -x509 -nodes `
    -newkey rsa:2048 -days $Days `
    -keyout /certs/privkey.pem -out /certs/fullchain.pem `
    -subj "/CN=$CommonName" `
    -addext "subjectAltName=DNS:$CommonName,DNS:localhost,IP:127.0.0.1"
if ($LASTEXITCODE -ne 0) { throw "openssl failed" }

Write-Host "[tls] certificate: $cert"
Write-Host "[tls] key:         $key"
