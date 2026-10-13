$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'First create backend/.venv and install dependencies as described in README.md.'
}
& $pythonPath (Join-Path $projectRoot 'backend\scripts\run_local.py')
exit $LASTEXITCODE
