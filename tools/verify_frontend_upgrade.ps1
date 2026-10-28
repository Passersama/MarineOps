$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$validation=Join-Path $taskRoot 'artifacts\validation-1.1.6'
$installed=Join-Path $validation ('upgrade from 1.1.5 '+[DateTime]::UtcNow.Ticks)
$data=Join-Path $validation ('legacy data '+[DateTime]::UtcNow.Ticks)
New-Item -ItemType Directory -Force $data | Out-Null
$legacy=Get-Content -LiteralPath (Join-Path $taskRoot 'output\audit-fixes-20261007\ui-final\native-visible.json') -Raw | ConvertFrom-Json
foreach ($name in @('cargo-track.sqlite3','personnel-transfer.sqlite3')) {
    Copy-Item -LiteralPath (Join-Path $legacy.data_directory $name) -Destination (Join-Path $data $name)
}
$oldSetup=Join-Path $taskRoot 'release\CargoTrack-Setup-1.1.5.exe'
$newSetup=Join-Path $taskRoot 'release\CargoTrack-Setup-1.1.6.exe'
$arguments='--install-dir "'+$installed+'" --quiet --no-launch --no-shortcut'
$old=Start-Process -FilePath $oldSetup -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
if ($old.ExitCode -ne 0) { throw 'Could not prepare the old installed version' }
$exe=Join-Path $installed 'CargoTrack\CargoTrack.exe'
$python=Join-Path $taskRoot '.venv-package\Scripts\python.exe'
$capture=Join-Path $taskRoot 'output\audit-fixes-20261007\capture_business.py'
$before=& $python $capture $data | ConvertFrom-Json
$env:CARGO_TRACK_DATA_DIR=$data
$env:CARGO_TRACK_TRACE='1'
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class AuditUpgradeWindow {
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window,int command);
 [DllImport("user32.dll")] private static extern bool EnumWindows(Callback callback,IntPtr value);
 [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr window,StringBuilder text,int length);
 private delegate bool Callback(IntPtr window,IntPtr value);
 public static IntPtr Find(uint process,string expected) {
   IntPtr result=IntPtr.Zero;
   EnumWindows(delegate(IntPtr window,IntPtr value) {
     uint owner; GetWindowThreadProcessId(window,out owner);
     if (owner==process) {
       StringBuilder title=new StringBuilder(512); GetWindowText(window,title,512);
       if (title.ToString()==expected) { result=window; return false; }
     }
     return true;
   },IntPtr.Zero);
   return result;
 }
}
'@
function Invoke-UpgradeWindowCheck([string]$expected) {
    $process=Start-Process -FilePath $exe -ArgumentList '--personnel' -WindowStyle Hidden -PassThru
    try {
        $window=[IntPtr]::Zero
        for ($attempt=0;$attempt -lt 60;$attempt++) {
            Start-Sleep -Milliseconds 250
            $process.Refresh()
            if ($process.HasExited) { throw ('App exited while opening '+$expected) }
            $window=[AuditUpgradeWindow]::Find($process.Id,('Cargo Track '+$expected))
            if ($window -ne [IntPtr]::Zero) { break }
        }
        if ($window -eq [IntPtr]::Zero) { throw 'Expected native app window was not opened' }
        [void][AuditUpgradeWindow]::ShowWindow($window,5)
        Start-Sleep -Seconds 2
        if (![AuditUpgradeWindow]::IsWindowVisible($window)) { throw 'Native upgrade window is not visible' }
        $process.Refresh()
        [void]$process.CloseMainWindow()
        if (!$process.WaitForExit(15000) -or $process.ExitCode -ne 0) { throw 'Upgrade app did not close cleanly' }
    } finally { if (!$process.HasExited -and $process.Path -eq $exe) { Stop-Process -Id $process.Id } }
}
Invoke-UpgradeWindowCheck '1.1.5'
$oldVersion=(Get-Item -LiteralPath $exe).VersionInfo.FileVersion
$upgrade=Start-Process -FilePath $newSetup -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
if ($upgrade.ExitCode -ne 0) { throw 'Upgrade installer failed' }
Invoke-UpgradeWindowCheck '1.1.6'
$after=& $python $capture $data | ConvertFrom-Json
foreach ($name in @('cargo-track.sqlite3','personnel-transfer.sqlite3')) {
    if ($before.$name.sha256 -ne $after.$name.sha256) { throw ('Upgrade changed business rows: '+$name) }
}
# A valid legacy database inside the program tree must block upgrade before any file replacement.
$protected=Join-Path $installed 'CargoTrack\_internal\custom-data.bin'
Copy-Item -LiteralPath (Join-Path $data 'personnel-transfer.sqlite3') -Destination $protected
$exeBefore=(Get-FileHash -LiteralPath $exe).Hash
$dbBefore=(Get-FileHash -LiteralPath $protected).Hash
$refused=Start-Process -FilePath $newSetup -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
if ($refused.ExitCode -eq 0 -or (Get-FileHash -LiteralPath $exe).Hash -ne $exeBefore -or (Get-FileHash -LiteralPath $protected).Hash -ne $dbBefore) { throw 'Installer failed to protect a nested SQLite business file' }
$report=@{from_version=$oldVersion;to_version=(Get-Item -LiteralPath $exe).VersionInfo.FileVersion;
    installed_upgrade='PASS';legacy_cargo_business_rows='UNCHANGED';legacy_personnel_business_rows='UNCHANGED';
    nested_database_install_guard='PASS';legacy_data_directory=$data;installed_directory=$installed;
    before=$before;after=$after;scope='Isolated workspace install and legacy data copies'}
$report | ConvertTo-Json -Depth 7 | Set-Content -Encoding UTF8 (Join-Path $validation 'upgrade-1.1.5-to-1.1.6.json')
$report | ConvertTo-Json -Depth 7
