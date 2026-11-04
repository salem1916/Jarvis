$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $PSScriptRoot "start_jarvis.ps1"
$ShortcutPath = Join-Path $env:USERPROFILE "Desktop\JARVIS.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)

$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.IconLocation = "shell32.dll,44"
$Shortcut.WindowStyle = 7
$Shortcut.Save()

Write-Host "Created desktop shortcut: $ShortcutPath"
