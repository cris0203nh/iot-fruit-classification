param(
    [Parameter(Mandatory = $true)] [string]$VercelOrigin
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$data = Join-Path $root '.agroscan_demo\data'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Falta backend/.venv/Scripts/python.exe; usar el entorno virtual actual.' }
if (-not (Test-Path -LiteralPath (Join-Path $data 'agroscan.db') -PathType Leaf)) { throw 'Primero crear copia aislada con agroscan_demo_prepare.py --create.' }
if ($VercelOrigin -notmatch '^https://[a-zA-Z0-9.-]+(?::443)?/?$') { throw 'VercelOrigin debe ser un origen HTTPS sin ruta ni query.' }
$env:AGROSCAN_DEMO_ORIGINS = $VercelOrigin.TrimEnd('/')
$env:AGROSCAN_DATA_DIR = $data
# Clave JWT efimera solo para el proceso de demostracion; no reutiliza la de backend/.env.
$jwtBytes = New-Object byte[] 48
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $generator.GetBytes($jwtBytes) } finally { $generator.Dispose() }
$env:AGROSCAN_JWT_SECRET = [Convert]::ToBase64String($jwtBytes)
$originalData = Join-Path $root 'backend\data'
$v2models = Join-Path $originalData 'ag055_v2\models'
if (Test-Path -LiteralPath $v2models -PathType Container) { $env:AGROSCAN_V2_MODELS_PATH = $v2models }
$qualityModels = Join-Path $originalData 'quality_models'
if (Test-Path -LiteralPath $qualityModels -PathType Container) { $env:AGROSCAN_QUALITY_MODELS_PATH = $qualityModels }
Write-Host 'FastAPI en 127.0.0.1:8000, usando COPIA PRIVADA de SQLite/fotos.'
Write-Host 'Los modelos originales permanecen en su carpeta y solo se leen.'
Push-Location (Join-Path $root 'backend')
try { & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 }
finally { Pop-Location }
