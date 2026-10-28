param([string]$Version='1.2.4',[string]$PreviousVersion='1.2.3')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$validation=Join-Path $taskRoot ('artifacts/validation-'+$Version)
$run=Join-Path $validation ('text-case-'+[DateTime]::UtcNow.Ticks)
New-Item -ItemType Directory -Force $run | Out-Null
$installed=Join-Path $run 'installed'
$portable=Join-Path $run 'portable'
$data=Join-Path $run 'fictional-data'
$env:TMP=Join-Path $taskRoot ('artifacts/validation-'+$Version+'/tmp')
New-Item -ItemType Directory -Force $env:TMP | Out-Null
$env:TEMP=$env:TMP
$legacy=Join-Path $taskRoot 'artifacts/validation-1.2.3/print-legs-639285591682494470/fictional-data'
if (!(Test-Path -LiteralPath (Join-Path $legacy 'fixture-metadata.json'))) {throw 'Archived fictional 1.2.3 fixture is unavailable'}
New-Item -ItemType Directory -Force $data | Out-Null
foreach ($name in @('cargo-track.sqlite3','personnel-transfer.sqlite3','fixture-metadata.json')) {
    Copy-Item -LiteralPath (Join-Path $legacy $name) -Destination (Join-Path $data $name)
}
$hashes=@{}
foreach ($name in @('cargo-track.sqlite3','personnel-transfer.sqlite3')) {
    $hashes[$name]=(Get-FileHash -LiteralPath (Join-Path $data $name)).Hash
}
$arguments='--install-dir "'+$installed+'" --quiet --no-launch --no-shortcut'
foreach ($installVersion in @($PreviousVersion,$Version)) {
    $setup=Join-Path $taskRoot ('release/CargoTrack-Setup-'+$installVersion+'.exe')
    $process=Start-Process -FilePath $setup -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
    if ($process.ExitCode -ne 0) {throw ('Installation failed: '+$installVersion)}
    if ((Get-Item (Join-Path $installed 'CargoTrack/CargoTrack.exe')).VersionInfo.FileVersion -ne $installVersion) {throw 'Installed version mismatch'}
}
Expand-Archive -LiteralPath (Join-Path $taskRoot ('release/CargoTrack-'+$Version+'-Windows-x64.zip')) -DestinationPath $portable
$env:CARGO_TRACK_DATA_DIR=$data
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class PrintLegsWindow {
    private delegate bool Callback(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] private static extern bool EnumWindows(Callback cb, IntPtr p);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    public static IntPtr Find(uint pid,string expected) {
        IntPtr found=IntPtr.Zero;
        EnumWindows(delegate(IntPtr h,IntPtr p) {uint owner;GetWindowThreadProcessId(h,out owner);
            if(owner==pid) {var s=new StringBuilder(512);GetWindowText(h,s,512);
                if(s.ToString()==expected) {found=h;return false;}}
            return true;},IntPtr.Zero);
        return found;
    }
    public static bool HasPersonnelError(uint pid) {
        bool found=false;
        EnumWindows(delegate(IntPtr h,IntPtr p) {uint owner;GetWindowThreadProcessId(h,out owner);
            if(owner==pid) {var s=new StringBuilder(512);GetWindowText(h,s,512);
                if(s.ToString().Contains("could not open") || s.ToString()=="Personnel Transfer Track") {found=true;return false;}}
            return true;},IntPtr.Zero);
        return found;
    }
}
'@
$fixture=Get-Content -LiteralPath (Join-Path $data 'fixture-metadata.json') -Raw | ConvertFrom-Json
if (!$fixture.removed_leg_history_preserved -or !$fixture.legacy_removed_reference_differs_from_current_parent) {throw 'Legacy removed-leg fixture is missing'}
$report=[ordered]@{version=$Version;standalone_installer='PASS';previous_version=$PreviousVersion;upgrade='PASS';legacy_fixture_origin=$legacy;fictional_data=$true;data_directory=$data;fixture=$fixture;packages=@()}
foreach ($edition in @('installed','portable')) {
    $exe=Join-Path (Join-Path $run $edition) 'CargoTrack/CargoTrack.exe'
    $process=Start-Process -FilePath $exe -ArgumentList '--personnel' -WindowStyle Hidden -PassThru
    try {
        $ready=$false
        for ($attempt=0;$attempt -lt 60;$attempt++) {
            Start-Sleep -Milliseconds 250
            $process.Refresh()
            if ($process.HasExited) {throw 'Packaged app exited unexpectedly'}
            $window=[PrintLegsWindow]::Find($process.Id,('Cargo Track '+$Version))
            if ($window -ne [IntPtr]::Zero) {$ready=$true;break}
        }
        if (!$ready) {throw 'Native Personnel window did not open'}
        Start-Sleep -Milliseconds 1500
        if ([PrintLegsWindow]::HasPersonnelError($process.Id)) {throw 'Packaged Personnel displayed a startup error'}
        $second=Start-Process -FilePath $exe -WindowStyle Hidden -PassThru
        if (!$second.WaitForExit(15000) -or $second.ExitCode -ne 0) {throw 'Single instance check failed'}
        [void][PrintLegsWindow]::PostMessage($window,0x0010,[IntPtr]::Zero,[IntPtr]::Zero)
        if (!$process.WaitForExit(15000) -or $process.ExitCode -ne 0) {throw 'Native app did not close cleanly'}
        foreach ($name in $hashes.Keys) {
            if ((Get-FileHash -LiteralPath (Join-Path $data $name)).Hash -ne $hashes[$name]) {throw ('Database changed: '+$name)}
        }
        $report.packages+=@{edition=$edition;native_personnel_launch='PASS';single_instance='PASS';clean_close='PASS';databases_unchanged=$true;sha256=(Get-FileHash -LiteralPath $exe).Hash}
    } finally {if (!$process.HasExited -and $process.Path -eq $exe) {Stop-Process -Id $process.Id}}
}
$report | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $validation 'text-case-packaged-validation.json')
$report | ConvertTo-Json -Depth 6
