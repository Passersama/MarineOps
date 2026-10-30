param([Parameter(Mandatory=$true)][string]$PreviousVersion,[string]$PythonPath='')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
if (!$PythonPath) {$PythonPath=Join-Path $taskRoot '.venv-package/Scripts/python.exe'}
$version=(& $PythonPath -c "import sys; sys.path.insert(0,'src'); from cargo_track import __version__; print(__version__)" | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {throw 'Could not determine the current version'}
foreach ($v in @($PreviousVersion,$version)) {
    $prefix=if ([Version]$v -ge [Version]'1.2.5') {'MarineOps'} else {'CargoTrack'}
    foreach ($name in @("${prefix}-Setup-${v}.exe","${prefix}-${v}-Windows-x64.zip")) {
        if (!(Test-Path -LiteralPath (Join-Path $taskRoot ('release/'+$name)))) {throw ('Required package is missing: '+$name)}
    }
}
$fixture=Join-Path $taskRoot ('artifacts/validation-'+$version+'/fixture-'+[DateTime]::UtcNow.Ticks)
$env:TMP=Join-Path $taskRoot '.tmp-build';$env:TEMP=$env:TMP
& $PythonPath (Join-Path $taskRoot 'tools/create_release_fixture.py') $fixture
if ($LASTEXITCODE -ne 0) {throw 'Could not create the isolated fictional fixture'}
& (Join-Path $taskRoot 'tools/verify_crew_sync_release.ps1') -Version $version -PreviousVersion $PreviousVersion -FixtureDirectory $fixture
