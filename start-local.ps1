param(
    [int]$Port = 5173,
    [string]$Database = 'backend/profitleak.db'
)
$ErrorActionPreference = 'Stop'
$localPython = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $localPython)) {
    throw 'Create backend/.venv and install ./backend as described in docs/LOCAL_RELEASE.md.'
}
& $localPython (Join-Path $PSScriptRoot 'backend\scripts\start_desktop.py') --port $Port --database $Database
exit $LASTEXITCODE
