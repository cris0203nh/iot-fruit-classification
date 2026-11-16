param(
    [Parameter(Mandatory = $true)] [string]$VercelOrigin
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Falta backend/.venv/Scripts/python.exe.' }
& $python (Join-Path $PSScriptRoot 'agroscan_demo_gateway.py') --origin $VercelOrigin --listen-port 8787 --upstream-port 8000
