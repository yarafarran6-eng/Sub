# Puts a "مترجم الروايات" shortcut with the site logo on your desktop. It runs start.bat from the site folder.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'مترجم الروايات.lnk'
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = Join-Path $root 'start.bat'
$s.WorkingDirectory = $root
$s.IconLocation = (Join-Path $root 'assets\logo.ico') + ',0'
$s.Description = 'مترجم الروايات'
$s.WindowStyle = 1
$s.Save()
Write-Host ''
Write-Host "تم: وضعت اختصار «مترجم الروايات» على سطح المكتب." -ForegroundColor Green
Write-Host "اضغط عليه مرتين لتشغيل الموقع (يفتح المتصفح لحاله)."
