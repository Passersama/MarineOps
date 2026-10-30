param([string]$PythonPath='', [switch]$SkipNative,[ValidateRange(1,8)][int]$Jobs=1)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
if (!$PythonPath) {$PythonPath=Join-Path $taskRoot '.venv-package/Scripts/python.exe'}
$checkArguments=@((Join-Path $taskRoot 'tools/check_project.py'))
$checkArguments+=@('--jobs',[string]$Jobs)
if ($SkipNative) {$checkArguments+='--skip-native'}
& $PythonPath @checkArguments
if ($LASTEXITCODE -ne 0) {throw 'Project checks failed; see the versioned output/checks directory'}
