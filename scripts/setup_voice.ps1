param([string]$Python = "3.13")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $UvExe = if ($UvCommand) { $UvCommand.Source } else { Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe' }
    if (-not (Test-Path -LiteralPath $UvExe)) { throw 'Install uv, then run this setup again.' }
    & $UvExe venv --python $Python .voice-venv --allow-existing
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python 3.13 speech environment.' }
    & $UvExe pip install --python .voice-venv/Scripts/python.exe -r scripts/voice-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Speech dependencies could not be installed.' }
    & .voice-venv/Scripts/python.exe scripts/download_voice_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Voice models could not be downloaded. Run setup again to resume.' }
    Write-Host 'Voice is ready. Restart Jarvis, enable Voice replies, then hold Talk.'
} finally {
    Pop-Location
}
