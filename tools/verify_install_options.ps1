$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$validationRoot = Join-Path $taskRoot 'artifacts\validation-1.0.5'
New-Item -ItemType Directory -Force $validationRoot | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$assembly = [Reflection.Assembly]::LoadFile((Join-Path $taskRoot 'release\CargoTrack-Setup-1.0.5.exe'))
$flags = [Reflection.BindingFlags]'Instance,NonPublic,Public'
$optionsType = $assembly.GetType('InstallOptions')
$options = [Activator]::CreateInstance($optionsType, $flags, $null, [object[]]@('D:\Apps\Cargo Track', $true, $true), $null)
try {
    $pathBox = $optionsType.GetField('PathInput', $flags).GetValue($options)
    $pathBox.Text = Join-Path $validationRoot 'Chosen folder Cargo Track'
    $optionsType.GetField('ShortcutOption', $flags).GetValue($options).Checked = $false
    $optionsType.GetField('LaunchOption', $flags).GetValue($options).Checked = $false
    $options.StartPosition = [Windows.Forms.FormStartPosition]::Manual
    $options.Location = New-Object Drawing.Point(-10000,-10000)
    $selectedPath = $pathBox.Text
    $button = $optionsType.GetField('InstallButton', $flags).GetValue($options)
    $timer = New-Object Windows.Forms.Timer
    $timer.Interval = 100
    $timer.Add_Tick({
        $timer.Stop()
        $bitmap = New-Object Drawing.Bitmap($options.Width, $options.Height)
        try { $options.DrawToBitmap($bitmap, (New-Object Drawing.Rectangle(0,0,$options.Width,$options.Height))); $bitmap.Save((Join-Path $validationRoot 'installer-options.png')) } finally { $bitmap.Dispose() }
        $button.PerformClick()
    })
    $timer.Start()
    try { $options.ShowDialog() | Out-Null } finally { $timer.Dispose() }
    if ($options.DialogResult -ne [Windows.Forms.DialogResult]::OK) { throw 'Install selection was not accepted' }
    if ($optionsType.GetProperty('InstallPath',$flags).GetValue($options,$null) -ne $pathBox.Text) { throw 'Selected path was lost' }
    if ($optionsType.GetProperty('CreateDesktopShortcut',$flags).GetValue($options,$null)) { throw 'Shortcut setting was lost' }
    if ($optionsType.GetProperty('LaunchAfterInstall',$flags).GetValue($options,$null)) { throw 'Launch setting was lost' }
} finally { $options.Dispose() }
$installer = Start-Process -FilePath (Join-Path $taskRoot 'release\CargoTrack-Setup-1.0.5.exe') -ArgumentList ('--quiet --no-shortcut --no-launch --install-dir "'+$selectedPath+'"') -WindowStyle Hidden -PassThru -Wait
if ($installer.ExitCode -ne 0 -or !(Test-Path -LiteralPath (Join-Path $selectedPath 'CargoTrack\CargoTrack.exe'))) { throw 'Custom folder installation failed' }
$guard = $assembly.GetType('Installer').GetMethod('ValidateInstallTarget',[Reflection.BindingFlags]'Static,NonPublic')
$unrelated = Join-Path $validationRoot 'unrelated-folder'
New-Item -ItemType Directory -Force $unrelated | Out-Null
Set-Content -LiteralPath (Join-Path $unrelated 'keep.txt') -Value 'Retain unrelated data'
$rejected = $false
try { $guard.Invoke($null,[object[]]@($unrelated)) | Out-Null } catch { $rejected = $true }
if (!$rejected -or !(Test-Path -LiteralPath (Join-Path $unrelated 'keep.txt'))) { throw 'Unrelated directory guard failed' }
$driveRejected = $false
try { $guard.Invoke($null,[object[]]@('E:\')) | Out-Null } catch { $driveRejected = $true }
if (!$driveRejected) { throw 'Drive root guard failed' }
$cancel = [Activator]::CreateInstance($optionsType,$flags,$null,[object[]]@('D:\Apps\Cargo Track',$true,$true),$null)
try { $cancel.CancelButton.GetType().GetMethod('OnClick', [Reflection.BindingFlags]'Instance,NonPublic').Invoke($cancel.CancelButton,[object[]]@([EventArgs]::Empty)) | Out-Null; if ($cancel.DialogResult -ne [Windows.Forms.DialogResult]::Cancel) { throw 'Cancel failed' } } finally { $cancel.Dispose() }
@{selected_folder='PASS';custom_folder_installation='PASS';shortcut_and_launch_options='PASS';cancel='PASS';unrelated_folder_protection='PASS';drive_root_protection='PASS'} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $validationRoot 'install-options-validation.json')
Write-Output 'PASS: path selection, options, cancel and existing-folder protection.'

