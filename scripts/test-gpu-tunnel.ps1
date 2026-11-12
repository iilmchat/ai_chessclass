# S-96: проверка GPU-туннеля (LM Studio за SSH reverse tunnel).
# Запуск с сервера/хоста: .\scripts\test-gpu-tunnel.ps1 `
#   -BaseUrl http://172.18.0.1:8035/v1 -ApiKey '<LM Studio token>'
# Ключ не выводится. Exit: 0 — OK, 1 — ошибка/таймаут.
param(
    [Parameter(Mandatory)][string]$BaseUrl,
    [string]$ApiKey = "",
    [string]$Model = "",
    [int]$TimeoutSec = 60
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")
if ($base -notmatch "/v1$") { $base = "$base/v1" }
$headers = @{}
if ($ApiKey) { $headers["Authorization"] = "Bearer $ApiKey" }

$rows = [System.Collections.Generic.List[object]]::new()
function Add-Row([string]$Check, [string]$Result, [string]$Details) {
    $rows.Add([pscustomobject]@{
        Check = $Check
        Result = $Result
        Details = $Details
    })
}

$failed = $false
try {
    $modelsResponse = Invoke-RestMethod -Method Get -Uri "$base/models" `
        -Headers $headers -TimeoutSec $TimeoutSec
    $modelIds = @($modelsResponse.data | ForEach-Object { $_.id })
    if ($modelIds.Count -eq 0) {
        Add-Row "models" "FAIL" "GET /v1/models: пустой список"
        $failed = $true
    } else {
        Add-Row "models" "OK" "models=$($modelIds.Count): $($modelIds -join ', ')"
        if (-not $Model) { $Model = [string]$modelIds[0] }
    }
} catch {
    Add-Row "models" "FAIL" "GET /v1/models: $($_.Exception.Message)"
    $failed = $true
}

if (-not $failed -and -not $Model) {
    Add-Row "chat" "FAIL" "не выбран model (LM Studio не вернул список)"
    $failed = $true
}

if (-not $failed) {
    $payload = @{
        model = $Model
        messages = @(
            @{
                role = "user"
                content = "Назови столицу Франции. Ответь одним словом."
            }
        )
        temperature = 0
        max_tokens = 32
    } | ConvertTo-Json -Depth 6
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $chat = Invoke-RestMethod -Method Post -Uri "$base/chat/completions" `
            -Headers $headers -ContentType "application/json" `
            -Body $payload -TimeoutSec $TimeoutSec
        $watch.Stop()
        $content = [string]$chat.choices[0].message.content
        $completion = 0
        if ($null -ne $chat.usage -and $null -ne $chat.usage.completion_tokens) {
            $completion = [int]$chat.usage.completion_tokens
        }
        $latencyMs = [math]::Round($watch.Elapsed.TotalMilliseconds, 1)
        $seconds = [math]::Max($watch.Elapsed.TotalSeconds, 0.001)
        $tps = [math]::Round($completion / $seconds, 2)
        if (-not $content.Trim()) {
            Add-Row "chat" "FAIL" "пустой content (model=$Model)"
            $failed = $true
        } else {
            Add-Row "chat" "OK" "model=$Model answer=$content"
            Add-Row "latency_ms" "OK" "$latencyMs ms"
            Add-Row "tokens_per_second" "OK" "$tps (completion=$completion)"
        }
    } catch {
        $watch.Stop()
        Add-Row "chat" "FAIL" "POST /v1/chat/completions: $($_.Exception.Message)"
        $failed = $true
    }
}

$rows | Format-Table -AutoSize | Out-String | Write-Host
if ($failed) {
    Write-Host "[gpu-tunnel] FAIL"
    exit 1
}
Write-Host "[gpu-tunnel] OK"
exit 0
