param([Parameter(Mandatory=$true)][ValidateSet('backend','frontend')][string]$Action)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dev = Join-Path $env:USERPROFILE 'Documents\AgroScan-Dev'
$python = Join-Path $env:USERPROFILE 'Documents\AgroScan-Python-Probe\Scripts\python.exe'
$secret = Join-Path $dev 'jwt.clixml'
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Falta el Python externo AgroScan-Python-Probe.' }
if (!(Test-Path -LiteralPath $dev -PathType Container) -or !(Test-Path -LiteralPath $secret -PathType Leaf)) {
    throw 'Falta el entorno DEV existente o su clave privada; no se copian bases ni se generan credenciales.'
}
$environment = @{
    AGROSCAN_DEV_ROOT=$dev; AGROSCAN_DATA_DIR=(Join-Path $dev 'data')
    AGROSCAN_DATABASE_URL=('sqlite:///' + $dev.Replace('\','/') + '/data/agroscan.db')
    AGROSCAN_JWT_SECRET=([PSCredential]::new('dev',(Import-Clixml -LiteralPath $secret))).GetNetworkCredential().Password
    AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP='true'; AGROSCAN_ENVIRONMENT='demo'
    AGROSCAN_SUBSCRIPTION_SIMULATOR='true'; AGROSCAN_SMTP_ENABLED='false'
    AGROSCAN_GOOGLE_CLIENT_ID=$env:AGROSCAN_GOOGLE_CLIENT_ID; AGROSCAN_DEMO_ORIGINS=''; VITE_API_BASE_URL=''
    PYTHONIOENCODING='utf-8'; PYTHONDONTWRITEBYTECODE='1'
    YOLO_CONFIG_DIR=(Join-Path $dev 'runtime\ultralytics')
    AGROSCAN_V2_MODELS_PATH=(Join-Path $dev 'data\ag055_v2\models')
}
$previous = @{}
try {
    foreach ($name in $environment.Keys) {
        $previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')
        [Environment]::SetEnvironmentVariable($name,$environment[$name],'Process')
    }
    Push-Location $root
    try {
        if ($Action -eq 'backend') {
            & $python tools/agroscan_dev.py prepare
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar desarrollo; no se inicia FastAPI.' }
            Write-Output 'Backend de desarrollo: 127.0.0.1:8000. Para detener: Ctrl+C.'
            & $python tools/agroscan_dev.py serve
        } else {
            & $python tools/agroscan_dev.py check
            if ($LASTEXITCODE -ne 0) { throw 'Desarrollo no preparado.' }
            Write-Output 'Navegador: http://localhost:5173. Para detener: Ctrl+C.'
            Push-Location (Join-Path $root 'frontend')
            try { & node.exe node_modules/vite/bin/vite.js --config vite.dev.config.ts } finally { Pop-Location }
        }
        if ($LASTEXITCODE -ne 0) { throw 'El servicio de desarrollo finalizo con error.' }
    } finally { Pop-Location }
} finally {
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name,$previous[$name],'Process') }
}
