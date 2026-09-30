param([switch]$UseActualDesktop)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$verificationRoot=Join-Path $taskRoot 'artifacts\validation-1.0.5'
$installDirectory=Join-Path $verificationRoot 'installed'
$setupDirectory=Join-Path $verificationRoot 'standalone-installer'
New-Item -ItemType Directory -Force $setupDirectory | Out-Null
$setupPath=Join-Path $setupDirectory 'CargoTrack-Setup-1.0.5.exe'
Copy-Item -LiteralPath (Join-Path $taskRoot 'release\CargoTrack-Setup-1.0.5.exe') -Destination $setupPath -Force
if ($UseActualDesktop) {
    $desktopDirectory=[Environment]::GetFolderPath('DesktopDirectory')
    $shortcutName='Cargo Track Validation 1.0.5'
} else {
    $desktopDirectory=Join-Path $verificationRoot 'test-desktop'
    $shortcutName='Cargo Track'
}
New-Item -ItemType Directory -Force $desktopDirectory | Out-Null
$shortcutPath=Join-Path $desktopDirectory ($shortcutName+'.lnk')
if ($UseActualDesktop -and (Test-Path -LiteralPath $shortcutPath)) { throw 'A validation shortcut already exists; do not overwrite it.' }
$arguments='--install-dir "'+$installDirectory+'" --desktop-dir "'+$desktopDirectory+'" --shortcut-name "'+$shortcutName+'" --quiet --no-launch'
$installer=Start-Process -FilePath $setupPath -ArgumentList $arguments -PassThru -Wait
if ($installer.ExitCode -ne 0) { throw "Installer returned $($installer.ExitCode)" }
if (!(Test-Path -LiteralPath $shortcutPath)) { throw 'Installer did not create the shortcut' }
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($shortcutPath)
$executable=Join-Path $installDirectory 'CargoTrack\CargoTrack.exe'
if ($shortcut.TargetPath -ne $executable) { throw 'Incorrect shortcut target' }
if ($shortcut.WorkingDirectory -ne (Split-Path -Parent $executable)) { throw 'Incorrect shortcut working directory' }
if ($shortcut.IconLocation -ne ($executable+',0')) { throw 'Shortcut does not use the branded application icon' }
$env:CARGO_TRACK_DATA_DIR=Join-Path $verificationRoot 'data'
& (Join-Path $taskRoot '.venv-package\Scripts\python.exe') (Join-Path $taskRoot 'tools\seed_validation.py')
if ($LASTEXITCODE -ne 0) { throw 'Failed to create isolated validation data' }
$before=(Get-FileHash (Join-Path $env:CARGO_TRACK_DATA_DIR 'cargo-track.sqlite3')).Hash
$upgrade=Start-Process -FilePath $setupPath -ArgumentList $arguments -PassThru -Wait
if ($upgrade.ExitCode -ne 0) { throw 'Upgrade test failed' }
$after=(Get-FileHash (Join-Path $env:CARGO_TRACK_DATA_DIR 'cargo-track.sqlite3')).Hash
if ($before -ne $after) { throw 'Installer changed the independent data file' }
Start-Process -FilePath $shortcutPath | Out-Null
Start-Sleep -Seconds 5
$running=@(Get-Process CargoTrack -ErrorAction SilentlyContinue | Where-Object Path -eq $executable)
if ($running.Count -ne 1) { throw 'Shortcut did not launch exactly one packaged application' }
$second=Start-Process -FilePath $executable -PassThru
Start-Sleep -Seconds 3
$second.Refresh()
if (!$second.HasExited -or $second.ExitCode -ne 0) { throw 'Repeat launch did not activate and exit' }
$report=[ordered]@{installer_exit=$installer.ExitCode;setup_is_standalone=$true;desktop_scope=$(if($UseActualDesktop){'Actual Windows Desktop'}else{'Workspace test desktop'});shortcut_path=$shortcutPath;shortcut_target=$shortcut.TargetPath;shortcut_working_directory=$shortcut.WorkingDirectory;shortcut_icon=$shortcut.IconLocation;shortcut_launch='PASS';upgrade_data_preservation='PASS';repeat_launch='PASS';running_pid=$running[0].Id;file_version=(Get-Item $executable).VersionInfo.FileVersion}
$report | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $verificationRoot $(if($UseActualDesktop){'actual-desktop-validation.json'}else{'installer-validation.json'}))
$report | ConvertTo-Json

