# S-93: SMTP smoke — локальный sink + реальный транспорт core.email.
# Проверяет verification и password-reset письма (plain SMTP sink).
# STARTTLS/SSL-режимы покрыты backend/tests/test_email.py (fake SMTP).
#
# Запуск: .\scripts\smtp-smoke.ps1
param(
    [string]$Network = "chessclass-net",
    [string]$Image = "chessclass/backend:dev",
    [int]$SinkPort = 1025
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$sinkName = "chessclass-smtp-smoke-sink"

docker rm -f $sinkName 2>$null | Out-Null
try {
    docker run -d --rm --name $sinkName --network $Network `
        -v "${root}/scripts/observability-smtp-sink.py:/sink.py:ro" `
        python:3.12-slim python /sink.py | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "не удалось запустить SMTP sink" }

    $deadline = (Get-Date).AddSeconds(30)
    do {
        $logs = (docker logs $sinkName 2>&1) -join "`n"
        if ($logs -match "SMTP sink ready") { break }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    if ($logs -notmatch "SMTP sink ready") { throw "SMTP sink не готов" }

    $script = @"
import asyncio
from core.email import password_reset_email, send_email, verification_email

async def main():
    subject, body = verification_email("https://example.test/verify?token=smoke")
    assert await send_email("verify-smoke@example.test", subject, body) is True
    subject, body = password_reset_email("https://example.test/reset?token=smoke")
    assert await send_email("reset-smoke@example.test", subject, body) is True

asyncio.run(main())
"@
    $tmp = Join-Path $root ".verify/smtp-smoke"
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $py = Join-Path $tmp "send.py"
    Set-Content -LiteralPath $py -Value $script -Encoding utf8

    docker run --rm --network $Network -w /srv/backend `
        -e PYTHONPATH=/srv/backend `
        -v "${py}:/tmp/send.py:ro" `
        -e SMTP_HOST=$sinkName -e SMTP_PORT=$SinkPort `
        -e SMTP_STARTTLS=false -e SMTP_SSL=false `
        -e SMTP_FROM=smoke@chessclass.dev `
        -e SMTP_USER= -e SMTP_PASSWORD= `
        $Image python /tmp/send.py 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "send_email failed" }

    $deadline = (Get-Date).AddSeconds(15)
    do {
        $logs = (docker logs $sinkName 2>&1) -join "`n"
        if ($logs -match "verify-smoke@example.test" -and
            $logs -match "reset-smoke@example.test") { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    if ($logs -notmatch "verify-smoke@example.test") {
        throw "verification-письмо не получено sink'ом"
    }
    if ($logs -notmatch "reset-smoke@example.test") {
        throw "password-reset письмо не получено sink'ом"
    }
    if ($logs -notmatch "Subject:") {
        throw "в sink нет SMTP-заголовков письма"
    }
    Write-Host "[smtp-smoke] verification + password-reset received (plain SMTP sink)"
} finally {
    docker rm -f $sinkName 2>$null | Out-Null
}
