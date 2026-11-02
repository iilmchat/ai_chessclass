# S-47: RS256-ключи для JWT (private/public PEM).
# Запуск: .\scripts\gen-jwt-keys.ps1 -Force
param(
    [string]$OutDir = "deploy/jwt",
    [int]$Bits = 2048,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$target = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $target | Out-Null
$private = Join-Path $target "private.pem"
$public = Join-Path $target "public.pem"
if ((Test-Path $private) -and -not $Force) {
    throw "keys exist: $private (use -Force)"
}
docker run --rm -v "${target}:/keys" alpine/openssl genpkey `
    -algorithm RSA -pkeyopt "rsa_keygen_bits:$Bits" -out /keys/private.pem
if ($LASTEXITCODE -ne 0) { throw "genpkey failed" }
docker run --rm -v "${target}:/keys" alpine/openssl rsa `
    -pubout -in /keys/private.pem -out /keys/public.pem
if ($LASTEXITCODE -ne 0) { throw "rsa pubout failed" }
Write-Host "[jwt] private: $private"
Write-Host "[jwt] public:  $public"
Write-Host "[jwt] задайте JWT_ALGORITHM=RS256 и пути/ключи в .env (не коммитить PEM)"
