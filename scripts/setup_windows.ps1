param(
    [string]$UvPath = "uv",
    [switch]$Voice,
    [switch]$SkipShortcut
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$UvCommand = Get-Command $UvPath -CommandType Application -ErrorAction Stop | Select-Object -First 1
$UvExe = $UvCommand.Source

Push-Location $ProjectRoot
try {
    & $UvExe sync --locked --no-dev
    if ($LASTEXITCODE -ne 0) { throw "Jarvis dependencies could not be installed." }

    $BasePython = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
    $PlannerFolder = Join-Path $ProjectRoot "experiments/browser-planner"
    $PlannerVenv = Join-Path $PlannerFolder ".venv"
    & $UvExe venv --python $BasePython --allow-existing $PlannerVenv
    if ($LASTEXITCODE -ne 0) { throw "The browser planner environment could not be created." }

    $PlannerPython = Join-Path $PlannerVenv "Scripts/python.exe"
    $PlannerLock = Join-Path $PlannerFolder "requirements.lock"
    & $UvExe pip sync --python $PlannerPython $PlannerLock
    if ($LASTEXITCODE -ne 0) { throw "Browser planner dependencies could not be installed." }

    if ($Voice) {
        & (Join-Path $PSScriptRoot "setup_voice.ps1") -UvPath $UvExe
    }
    if (-not $SkipShortcut) {
        & (Join-Path $PSScriptRoot "create_desktop_shortcut.ps1")
    }
    Write-Host "Jarvis is ready. Launch it with the shortcut or scripts/start_jarvis.ps1."
} finally {
    Pop-Location
}
