# S-82: внутренний CA и mTLS-сертификаты для prod-observability.
# Коллектор проверяет Tempo по этому CA, Tempo — клиентский сертификат
# коллектора. Ключи в git не попадают (deploy/internal-certs/.gitignore).
#
# Запуск: .\scripts\gen-internal-certs.ps1 [-Force] [-OutDir deploy/internal-certs] [-Days 825]
param(
    [string]$OutDir = "deploy/internal-certs",
    [int]$Days = 825,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$target = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $target | Out-Null

$caCrt = Join-Path $target "ca.crt"
if ((Test-Path $caCrt) -and -not $Force) {
    throw "certs exist: $caCrt (use -Force для перевыпуска)"
}

$image = "alpine/openssl"
$mount = "${target}:/certs"

function Invoke-OpenSsl {
    param([string[]]$OpenSslArgs)
    docker run --rm -v $mount $image @OpenSslArgs
    if ($LASTEXITCODE -ne 0) {
        throw "openssl failed: $($OpenSslArgs -join ' ')"
    }
}

# SAN для сервисов внутри chessclass-prod-net (+ loopback для отладки).
$san = "subjectAltName=DNS:tempo,DNS:otel-collector,DNS:localhost,IP:127.0.0.1"
$sanFile = Join-Path $target "san.ext"
$sanLines = @(
    $san,
    "extendedKeyUsage=serverAuth,clientAuth",
    "basicConstraints=critical,CA:FALSE",
    "keyUsage=critical,digitalSignature,keyEncipherment"
)
Set-Content -LiteralPath $sanFile -Value ($sanLines -join "`n") -NoNewline -Encoding ascii

# 1. Внутренний CA (RSA 4096, 825 дней).
Invoke-OpenSsl @(
    "req", "-x509", "-newkey", "rsa:4096", "-sha256", "-days", "$Days", "-nodes",
    "-keyout", "/certs/ca.key", "-out", "/certs/ca.crt",
    "-subj", "/CN=chessclass-internal-ca",
    "-addext", "basicConstraints=critical,CA:TRUE",
    "-addext", "keyUsage=critical,keyCertSign,cRLSign"
)

# 2. Серверные/клиентские сертификаты: tempo (TLS-терминатор) и collector (mTLS).
foreach ($name in @("tempo", "collector")) {
    Invoke-OpenSsl @(
        "req", "-newkey", "rsa:2048", "-sha256", "-nodes",
        "-keyout", "/certs/$name.key", "-out", "/certs/$name.csr",
        "-subj", "/CN=$name",
        "-addext", $san
    )
    Invoke-OpenSsl @(
        "x509", "-req", "-in", "/certs/$name.csr",
        "-CA", "/certs/ca.crt", "-CAkey", "/certs/ca.key", "-CAcreateserial",
        "-days", "$Days", "-sha256", "-extfile", "/certs/san.ext",
        "-out", "/certs/$name.crt"
    )
}

# 3. Уборка промежуточных файлов и приватность ключей.
Remove-Item -LiteralPath $sanFile -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $target -Filter "*.csr" | Remove-Item -Force
Get-ChildItem -LiteralPath $target -Filter "*.srl" | Remove-Item -Force

# 4. Права для non-root контейнеров (tempo/collector работают под uid 10001).
# На Linux chown реальный; на Docker Desktop для Windows режим/владелец
# транслируются, поэтому шаг идемпотентен и безопасен в обоих случаях.
docker run --rm -v $mount alpine:3 sh -c @'
chown -R 10001:10001 /certs 2>/dev/null || true
chmod 640 /certs/*.crt /certs/*.key 2>/dev/null || true
'@
if ($LASTEXITCODE -ne 0) {
    throw "не удалось выставить права на сертификаты"
}

Write-Host "[obs-certs] CA:        $caCrt"
foreach ($name in @("tempo", "collector")) {
    Write-Host "[obs-certs] $name : $((Join-Path $target "$name.crt")) / $name.key"
}
Write-Host "[obs-certs] SAN: $san"
Write-Host "[obs-certs] ключи не коммитить: deploy/internal-certs/ в .gitignore"
Write-Host "[obs-certs] перевыпуск при смене хостов: .\scripts\gen-internal-certs.ps1 -Force"
