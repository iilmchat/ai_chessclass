# S-96: автоподдержка обратного SSH-туннеля до GPU-станции (Windows).
# Запуск на Windows-ПК с LM Studio; цикл переподключения при обрыве.
# Пример: .\wg-gpu-tunnel.ps1 -ServerHost 203.0.113.10
param(
    [Parameter(Mandatory)][string]$ServerHost,
    [string]$SshUser = "root",
    [string]$RemoteBind = "172.18.0.1",
    [int]$RemotePort = 8035,
    [int]$LocalPort = 1234,
    [int]$RetrySeconds = 10
)

$ErrorActionPreference = "Continue"
Write-Host "[gpu-tunnel] station: $env:COMPUTERNAME; LM Studio 127.0.0.1:$LocalPort"
Write-Host "[gpu-tunnel] remote: ${SshUser}@${ServerHost}:${RemoteBind}:${RemotePort}"

while ($true) {
    $listening = Test-NetConnection -ComputerName 127.0.0.1 -Port $LocalPort `
        -InformationLevel Quiet -WarningAction SilentlyContinue
    if (-not $listening) {
        Write-Warning "[gpu-tunnel] LM Studio не слушает 127.0.0.1:$LocalPort; повтор через $RetrySeconds с"
        Start-Sleep -Seconds $RetrySeconds
        continue
    }

    $sshArgs = @(
        "-N",
        "-R", "${RemoteBind}:${RemotePort}:127.0.0.1:${LocalPort}",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ConnectTimeout=10",
        "${SshUser}@${ServerHost}"
    )
    Write-Host "[gpu-tunnel] ssh $($sshArgs -join ' ')"
    & ssh @sshArgs
    Write-Warning "[gpu-tunnel] SSH завершился (exit=$LASTEXITCODE); реконнект через $RetrySeconds с"
    Start-Sleep -Seconds $RetrySeconds
}
