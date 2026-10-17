param(
    [int]$Port = 5173,
    [string]$Database = 'backend/profitleak.db'
)
$ErrorActionPreference = 'Stop'
$localPython = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $localPython)) {
    throw 'Run 1_INSTALL.cmd first. Installation instructions: README.md.'
}
& $localPython (Join-Path $PSScriptRoot 'backend\scripts\start_desktop.py') --port $Port --database $Database
exit $LASTEXITCODE
