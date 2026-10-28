$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$validation=Join-Path $taskRoot 'artifacts\validation-1.2.0'
New-Item -ItemType Directory -Force $validation | Out-Null
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class PersonnelWindowCapture {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window,out Rect rect);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr window,IntPtr dc,uint flags);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
  [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window,int command);
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
        if (title.ToString()=="Cargo Track 1.2.0") { result=window; return false; }
      }
      return true;
    },IntPtr.Zero);
    return result;
  }
}
'@
[void][PersonnelWindowCapture]::SetThreadDpiAwarenessContext([IntPtr](-4))
$nativeReport=Get-Content -LiteralPath (Join-Path $taskRoot 'output\approved-ui-20261011\native-checks.json') -Raw | ConvertFrom-Json
$sourceData=$nativeReport.data_directory
$desktop=Join-Path $validation 'test-desktop'
$installed=Join-Path $validation 'installed'
$setup=Join-Path $taskRoot 'release\CargoTrack-Setup-1.2.0.exe'
$arguments='--install-dir "'+$installed+'" --desktop-dir "'+$desktop+'" --shortcut-name "Cargo Track 1.2.0 Validation" --quiet --no-launch'
$installer=Start-Process -FilePath $setup -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
if ($installer.ExitCode -ne 0) { throw 'Standalone installer failed' }
$shortcutPath=Join-Path $desktop 'Cargo Track 1.2.0 Validation.lnk'
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($shortcutPath)
$installedExe=Join-Path $installed 'CargoTrack\CargoTrack.exe'
if ($shortcut.TargetPath -ne $installedExe -or $shortcut.WorkingDirectory -ne (Split-Path -Parent $installedExe) -or $shortcut.IconLocation -ne ($installedExe+',0')) { throw 'Shortcut identity failed' }
$portable=Join-Path $validation ('portable extracted '+[DateTime]::UtcNow.Ticks)
if (Test-Path -LiteralPath $portable) { throw 'Use a fresh portable validation destination' }
Expand-Archive -LiteralPath (Join-Path $taskRoot 'release\CargoTrack-1.2.0-Windows-x64.zip') -DestinationPath $portable
$report=[ordered]@{standalone_installer='PASS';shortcut_target='PASS';scope='Workspace test desktop';packages=@()}
foreach ($item in @(@{kind='installed';exe=$installedExe},@{kind='portable';exe=(Join-Path $portable 'CargoTrack\CargoTrack.exe')})) {
    $data=Join-Path $validation ($item.kind+'-data')
    New-Item -ItemType Directory -Force $data | Out-Null
    Copy-Item -LiteralPath (Join-Path $sourceData 'cargo-track.sqlite3') -Destination (Join-Path $data 'cargo-track.sqlite3')
    Copy-Item -LiteralPath (Join-Path $sourceData 'personnel-transfer.sqlite3') -Destination (Join-Path $data 'personnel-transfer.sqlite3')
    $before=(Get-FileHash -LiteralPath (Join-Path $data 'cargo-track.sqlite3')).Hash
    $env:CARGO_TRACK_DATA_DIR=$data
    $env:CARGO_TRACK_TRACE='1'
    # Launch the installer-created shortcut as well as the extracted portable executable.
    $shortcut.Arguments='--personnel'
    if ($item.kind -eq 'installed') { $shortcut.Save(); Start-Process -FilePath $shortcutPath -WindowStyle Hidden | Out-Null }
    else { Start-Process -FilePath $item.exe -ArgumentList '--personnel' -WindowStyle Hidden | Out-Null }
    $running=$null
    $window=[IntPtr]::Zero
    for ($attempt=0;$attempt -lt 40;$attempt++) {
        Start-Sleep -Milliseconds 500
        $running=Get-Process CargoTrack -ErrorAction SilentlyContinue | Where-Object Path -eq $item.exe | Select-Object -First 1
        if ($running) { $window=[PersonnelWindowCapture]::Find($running.Id); if ($window -ne [IntPtr]::Zero) { break } }
    }
    if (!$running -or $window -eq [IntPtr]::Zero) { throw ($item.kind+' did not open its native window') }
    try {
        [void][PersonnelWindowCapture]::ShowWindow($window,5)
        Start-Sleep -Seconds 2
        $running.Refresh()
        if ($running.HasExited) { throw 'Packaged app exited unexpectedly' }
        $rect=New-Object PersonnelWindowCapture+Rect
        [void][PersonnelWindowCapture]::GetWindowRect($running.MainWindowHandle,[ref]$rect)
        $bitmap=New-Object Drawing.Bitmap(($rect.Right-$rect.Left),($rect.Bottom-$rect.Top))
        $graphics=[Drawing.Graphics]::FromImage($bitmap)
        $dc=$graphics.GetHdc()
        try { $captured=[PersonnelWindowCapture]::PrintWindow($running.MainWindowHandle,$dc,2) }
        finally { $graphics.ReleaseHdc($dc); $graphics.Dispose() }
        try { $bitmap.Save((Join-Path $validation ($item.kind+'-personnel.png'))) } finally { $bitmap.Dispose() }
        if (!$captured) { throw 'Native packaged window capture failed' }
        $second=Start-Process -FilePath $item.exe -WindowStyle Hidden -PassThru
        if (!$second.WaitForExit(15000) -or $second.ExitCode -ne 0) { throw 'Single-instance activation failed' }
        $report.packages+=@{edition=$item.kind;launch='PASS';native_window=$running.MainWindowTitle;visible=[PersonnelWindowCapture]::IsWindowVisible($running.MainWindowHandle);single_instance='PASS';cargo_hash_unchanged=$true;file_version=(Get-Item $item.exe).VersionInfo.FileVersion}
        [void]$running.CloseMainWindow()
        if (!$running.WaitForExit(15000)) { throw 'Packaged app did not close cleanly' }
        if ((Get-FileHash -LiteralPath (Join-Path $data 'cargo-track.sqlite3')).Hash -ne $before) { throw 'New Personnel page changed cargo database' }
    } finally { if ($running -and !$running.HasExited -and $running.Path -eq $item.exe) { Stop-Process -Id $running.Id } }
    if ($item.kind -eq 'installed') {
        $passengerBefore=(Get-FileHash -LiteralPath (Join-Path $data 'personnel-transfer.sqlite3')).Hash
        $upgrade=Start-Process -FilePath $setup -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
        if ($upgrade.ExitCode -ne 0 -or (Get-FileHash -LiteralPath (Join-Path $data 'personnel-transfer.sqlite3')).Hash -ne $passengerBefore) { throw 'Upgrade changed personnel data' }
        $report.upgrade_data_preservation='PASS'
    }
}
$shortcut.Arguments='--personnel'
$shortcut.Save()
$report | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $validation 'packaged-workspace-validation.json')
$report | ConvertTo-Json -Depth 5
