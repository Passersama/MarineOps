$ErrorActionPreference='Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$validationRoot = Join-Path $taskRoot 'artifacts\validation-1.0.5'
$extraction = Join-Path $validationRoot 'portable extracted'
if (Test-Path -LiteralPath $extraction) { throw 'Portable validation destination already exists' }
Expand-Archive -LiteralPath (Join-Path $taskRoot 'release\CargoTrack-1.0.5-Windows-x64.zip') -DestinationPath $extraction
$executable = Join-Path $extraction 'CargoTrack\CargoTrack.exe'
$env:CARGO_TRACK_DATA_DIR = Join-Path $validationRoot 'portable-data'
$process = Start-Process -FilePath $executable -WindowStyle Hidden -PassThru
try {
    Start-Sleep -Seconds 5
    $process.Refresh()
    if ($process.HasExited) { throw 'Extracted portable app exited unexpectedly' }
    if (!(Test-Path -LiteralPath (Join-Path $env:CARGO_TRACK_DATA_DIR 'cargo-track.sqlite3'))) { throw 'Portable app did not initialize its database' }
    if (!(Test-Path -LiteralPath (Join-Path $extraction 'CargoTrack\_internal\assets\help\user-guide.html'))) { throw 'Portable help is missing' }
    @{archive_extraction='PASS';extracted_executable_launch='PASS';database_creation='PASS';offline_help='PASS';file_version=(Get-Item $executable).VersionInfo.FileVersion} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $validationRoot 'portable-validation.json')
    Write-Output 'PASS: extracted portable app launched and initialized its isolated database.'
} finally { if (!$process.HasExited -and $process.Path -eq $executable) { Stop-Process -Id $process.Id } }
