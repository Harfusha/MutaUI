param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [Parameter(Mandatory = $true)]
    [string]$Label
)

$ErrorActionPreference = "Stop"
$logPath = Join-Path $env:TEMP "mutagen-control-self-test.log"
Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue

$process = Start-Process -FilePath $Executable -ArgumentList "--self-test" `
    -PassThru -WindowStyle Hidden
$completed = $process.WaitForExit(20000)

if ($completed) {
    $exitCode = $process.ExitCode
} else {
    $passedLog = (Test-Path -LiteralPath $logPath) -and
        ((Get-Content -LiteralPath $logPath -Raw).Trim() -eq "OK: UI pages and server groups rendered.")
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    if ($passedLog) {
        Write-Host "$Label self-test passed; stopped the lingering windowed process."
        $exitCode = 0
    } else {
        $exitCode = 124
    }
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
