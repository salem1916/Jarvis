param(
    [string]$BaseVenv,
    [string]$PlannerPython
)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot

# Start only Jarvis. Browser and voice workers are started on explicit use;
# choosing Groq must not also start a separate Hermes gateway in the background.
if (-not $BaseVenv) { $BaseVenv = Join-Path $ProjectRoot ".venv" }
$JarvisPython = Join-Path $BaseVenv "Scripts/python.exe"
if (-not (Test-Path -LiteralPath $JarvisPython -PathType Leaf)) {
    throw "Jarvis's Python environment is missing. Run the project setup first."
}

$env:JARVIS_BROWSER_MODE = "system"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
if (-not $PlannerPython) {
    $PlannerPython = Join-Path $ProjectRoot "experiments/browser-planner/.venv/Scripts/python.exe"
}
if (Test-Path -LiteralPath $PlannerPython -PathType Leaf) {
    $env:JARVIS_BASE_VENV = $BaseVenv
    $env:JARVIS_LAUNCH_DIR = Split-Path -Parent (Resolve-Path -LiteralPath $BaseVenv).Path
    $env:JARVIS_WINDOW_TITLE = "JARVIS - Current Chrome"
    & $PlannerPython (Join-Path $ProjectRoot "experiments/browser-planner/desktop_trial.py")
} else {
    & $JarvisPython -m jarvis.ui
}
exit $LASTEXITCODE
