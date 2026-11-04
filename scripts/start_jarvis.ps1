$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot

# Start only Jarvis. Browser and voice workers are started on explicit use;
# choosing Groq must not also start a separate Hermes gateway in the background.
$JarvisPython = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $JarvisPython -PathType Leaf)) {
    throw "Jarvis's Python environment is missing. Run the project setup first."
}

& $JarvisPython -m jarvis.ui
exit $LASTEXITCODE
