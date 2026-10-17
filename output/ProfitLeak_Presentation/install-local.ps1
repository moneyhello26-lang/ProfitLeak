param([string]$Python = '')

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$backendPath = Join-Path $projectRoot 'backend'

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Executable"
    }
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
        throw 'The frontend build is missing. Extract the complete presentation archive first.'
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $pythonCommand = $null
        $pythonArguments = @()
        if ($Python) {
            $pythonCommand = $Python
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            $pythonCommand = 'py'
            $pythonArguments = @('-3')
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            $pythonCommand = 'python'
        } else {
            throw 'Install Python 3.11 or newer from python.org, then run 1_INSTALL.cmd again.'
        }
        Invoke-Checked $pythonCommand ($pythonArguments + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'))
        Invoke-Checked $pythonCommand ($pythonArguments + @('-m', 'venv', (Join-Path $backendPath '.venv')))
    }
    Invoke-Checked $venvPython @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)')
    Invoke-Checked $venvPython @('-m', 'pip', 'install', $backendPath)
    Write-Host ''
    Write-Host 'Installation complete. Run 2_START.cmd and open http://127.0.0.1:5173'
    exit 0
} catch {
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'See README.md for installation steps and troubleshooting.'
    exit 1
}
