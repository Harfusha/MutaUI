param(
    [string]$Version = $(if ($env:MUTAGEN_TEST_VERSION) { $env:MUTAGEN_TEST_VERSION } else { '0.18.1' })
)

$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP 'mutagen-test-cli'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$archive = Join-Path $root "mutagen_windows_amd64_v$Version.zip"
$archiveName = "mutagen_windows_amd64_v$Version.zip"
$releaseUrl = "https://github.com/mutagen-io/mutagen/releases/download/v$Version"
$url = "$releaseUrl/$archiveName"
Invoke-WebRequest -Uri $url -OutFile $archive
$checksums = Join-Path $root 'SHA256SUMS'
Invoke-WebRequest -Uri "$releaseUrl/SHA256SUMS" -OutFile $checksums
$checksumLine = Get-Content -LiteralPath $checksums | Where-Object { $_ -match "^([0-9a-fA-F]{64})\s+$([regex]::Escape($archiveName))$" } | Select-Object -First 1
if ($null -eq $checksumLine) { throw "Official SHA-256 manifest has no entry for $archiveName." }
$expectedHash = ($checksumLine -split '\s+')[0].ToLowerInvariant()
$actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) { throw "SHA-256 verification failed for $archiveName." }
Expand-Archive -LiteralPath $archive -DestinationPath $root -Force
$binary = Get-ChildItem -LiteralPath $root -Filter mutagen.exe -File -Recurse | Select-Object -First 1
if ($null -eq $binary) { throw 'Mutagen executable was missing from the official release archive.' }
& $binary.FullName version
if ($LASTEXITCODE -ne 0) { throw "Mutagen version check failed: $LASTEXITCODE" }
"MUTAGEN_BINARY=$($binary.FullName)" | Add-Content -LiteralPath $env:GITHUB_ENV -Encoding utf8
