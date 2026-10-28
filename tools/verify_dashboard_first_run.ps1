$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$validation=Join-Path $taskRoot 'artifacts\validation-1.2.1'
$data=Join-Path $validation ('first-run-data-'+[DateTime]::UtcNow.Ticks)
New-Item -ItemType Directory -Path $data | Out-Null
$env:CARGO_TRACK_DATA_DIR=$data
$exe=Join-Path $validation 'installed\CargoTrack\CargoTrack.exe'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class DashboardFirstRun {
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window,out Rect rect);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr window,IntPtr dc,uint flags);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window,int command);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
 [DllImport("user32.dll")] private static extern bool EnumWindows(Callback callback,IntPtr value);
 [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr window,StringBuilder text,int length);
 private delegate bool Callback(IntPtr window,IntPtr value);
 public static IntPtr Find(uint process) {
   IntPtr result=IntPtr.Zero;
   EnumWindows(delegate(IntPtr window,IntPtr value) {
     uint owner; GetWindowThreadProcessId(window,out owner);
     if (owner==process) {
       StringBuilder title=new StringBuilder(512); GetWindowText(window,title,512);
       if (title.ToString()=="Cargo Track 1.2.1") { result=window; return false; }
     }
     return true;
   },IntPtr.Zero);return result;
 }
}
'@
$process=Start-Process -FilePath $exe -WindowStyle Hidden -PassThru
try {
    $window=[IntPtr]::Zero
    for ($attempt=0;$attempt -lt 60;$attempt++) {
        Start-Sleep -Milliseconds 250
        if ($process.HasExited) { throw 'First-run app exited unexpectedly' }
        $window=[DashboardFirstRun]::Find($process.Id)
        if ($window -ne [IntPtr]::Zero) { break }
    }
    if ($window -eq [IntPtr]::Zero) { throw 'First-run native window missing' }
    [void][DashboardFirstRun]::ShowWindow($window,5)
    Start-Sleep -Seconds 2
    if (![DashboardFirstRun]::IsWindowVisible($window)) { throw 'First-run window not visible' }
    $rect=New-Object DashboardFirstRun+Rect
    [void][DashboardFirstRun]::GetWindowRect($window,[ref]$rect)
    $bitmap=New-Object Drawing.Bitmap(($rect.Right-$rect.Left),($rect.Bottom-$rect.Top))
    $graphics=[Drawing.Graphics]::FromImage($bitmap);$dc=$graphics.GetHdc()
    try { $captured=[DashboardFirstRun]::PrintWindow($window,$dc,2) }
    finally { $graphics.ReleaseHdc($dc);$graphics.Dispose() }
    try { $bitmap.Save((Join-Path $validation 'first-run-dashboard.png')) } finally { $bitmap.Dispose() }
    if (!$captured) { throw 'First-run screenshot failed' }
    $process.Refresh();[void]$process.CloseMainWindow()
    if (!$process.WaitForExit(15000) -or $process.ExitCode -ne 0) { throw 'First-run close failed' }
    if (Test-Path -LiteralPath (Join-Path $data 'personnel-transfer.sqlite3')) { throw 'Dashboard created an unopened Personnel database' }
    & (Join-Path $taskRoot '.venv-package\Scripts\python.exe') -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('SELECT count(*) FROM transfer_legs').fetchone()[0]==0; print('PASS')" (Join-Path $data 'cargo-track.sqlite3')
    if ($LASTEXITCODE -ne 0) { throw 'First-run empty ledger invalid' }
    @{result='PASS';empty_ledger=$true;personnel_database_not_created=$true;native_default_dashboard=$true;directory=$data} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $validation 'first-run-validation.json')
} finally { if (!$process.HasExited -and $process.Path -eq $exe) { Stop-Process -Id $process.Id } }
