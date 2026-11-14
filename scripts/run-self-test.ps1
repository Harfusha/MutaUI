param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [Parameter(Mandatory = $true)]
    [string]$Label
)

$ErrorActionPreference = "Stop"
$logDirectory = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$logPath = Join-Path $logDirectory "mutagen-control-self-test.log"
Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
$env:MUTAUI_SELF_TEST_LOG = $logPath

$process = Start-Process -FilePath $Executable -ArgumentList "--self-test" `
    -PassThru -WindowStyle Hidden
$deadline = [DateTime]::UtcNow.AddSeconds(120)
$completed = $false
$passedLog = $false
while ([DateTime]::UtcNow -lt $deadline) {
    $completed = $process.WaitForExit(250)
    if ((Test-Path -LiteralPath $logPath) -and
        ((Get-Content -LiteralPath $logPath -Raw).Trim() -eq "OK: UI pages and server groups rendered.")) {
        $passedLog = $true
        break
    }
    if ($completed) { break }
}

if ($passedLog) {
    if (-not $completed) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "$Label self-test passed."
    $exitCode = 0
} elseif ($completed) {
    $exitCode = $process.ExitCode
} else {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    $exitCode = 124
}

if ($exitCode -ne 0) {
    if (Test-Path -LiteralPath $logPath) {
        Write-Host "=== $Label EXE self-test log ==="
        Get-Content -LiteralPath $logPath
    } else {
        Write-Host "Self-test log not created: $logPath"
    }
    throw "$Label EXE self-test failed (exit code $exitCode)"
}
