param(
    [Parameter(Mandatory=$true)] [ValidateSet('init','start','stop','status','credentials','verify')] [string]$Action,
    [ValidateSet('propietario','administrador','operador','revisor')] [string]$Role,
    [switch]$Reveal
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qa = Join-Path $root '.agroscan-qa'
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$manifestPath = Join-Path $qa 'manifest.json'
$secretPath = Join-Path $qa 'access.clixml'

function New-RandomSecret {
    $bytes = New-Object byte[] 48
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes)
}
function Get-PrivateAccess {
    if (!(Test-Path -LiteralPath $secretPath)) { throw 'Falta inicializar QA.' }
    return Import-Clixml -LiteralPath $secretPath
}
function Invoke-QaEnvironment([scriptblock]$Operation) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $access = Get-PrivateAccess
    $data = Join-Path $qa 'data'
    $environment = @{
        AGROSCAN_QA_ROOT=$qa; AGROSCAN_QA_INSTANCE=$manifest.instance
        AGROSCAN_DATA_DIR=$data; AGROSCAN_DATABASE_URL=('sqlite:///' + $data.Replace('\','/') + '/agroscan.db')
        AGROSCAN_JWT_SECRET=([PSCredential]::new('jwt',$access.Jwt)).GetNetworkCredential().Password
        AGROSCAN_ENVIRONMENT='demo'; AGROSCAN_SUBSCRIPTION_SIMULATOR='true'
        AGROSCAN_GOOGLE_CLIENT_ID='qa-disabled'; AGROSCAN_DEMO_ORIGINS=''
        VITE_API_BASE_URL=''; PYTHONIOENCODING='utf-8'
    }
    $previous = @{}
    try {
        foreach ($name in $environment.Keys) { $previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process'); [Environment]::SetEnvironmentVariable($name,$environment[$name],'Process') }
        Push-Location $root
        try { & $Operation } finally { Pop-Location }
    } finally {
        foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name,$previous[$name],'Process') }
    }
}
function Assert-FreePort([int]$Port) {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback,$Port)
    try { $listener.Start() } catch { throw "Puerto $Port ocupado. No se detiene ni reutiliza otro servicio." } finally { $listener.Stop() }
}
function Save-ProcessRecord($Process, [string]$Kind) {
    @{ pid=$Process.Id; started=$Process.StartTime.ToUniversalTime().ToString('o'); kind=$Kind } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $qa ($Kind+'.process.json')) -Encoding UTF8
}
function Stop-QaProcess([string]$Kind) {
    $recordPath = Join-Path $qa ($Kind+'.process.json')
    if (!(Test-Path -LiteralPath $recordPath)) { return }
    $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (!$process) { return }
    if ($process.StartTime.ToUniversalTime().ToString('o') -ne $record.started) { throw 'PID reutilizado; no se detendrá otro proceso.' }
    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.pid)"
    $expected = if ($Kind -eq 'backend') { 'agroscan_qa.py serve' } else { 'vite.qa.config.ts' }
    if (!$details.CommandLine.Contains($expected)) { throw 'Proceso distinto al registrado; no se detendrá.' }
    function Stop-Children([int]$Parent) {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $Parent")
        foreach ($child in $children) { Stop-Children $child.ProcessId; Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
    }
    Stop-Children $record.pid
    Stop-Process -Id $record.pid -ErrorAction SilentlyContinue
}

switch ($Action) {
    'init' {
        if ((Test-Path -LiteralPath $manifestPath) -or (Test-Path -LiteralPath (Join-Path $qa 'data/agroscan.db'))) { throw 'QA ya existe; no se reinicia ni sobrescribe.' }
        & git -C $root check-ignore --quiet -- '.agroscan-qa/access.clixml'
        if ($LASTEXITCODE -ne 0) { throw 'La carpeta QA debe estar ignorada antes de crear credenciales.' }
        New-Item -ItemType Directory -Force -Path $qa | Out-Null
        $acl = New-Object System.Security.AccessControl.DirectorySecurity
        $acl.SetAccessRuleProtection($true,$false)
        $userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
        foreach ($sid in @($userSid, [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18'), [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))) {
            $acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
        }
        Set-Acl -LiteralPath $qa -AclObject $acl
        New-Item -ItemType Directory -Force -Path (Join-Path $qa 'frontend-env') | Out-Null
        $accounts = @{}
        foreach ($name in @('propietario','administrador','operador','revisor')) {
            $accounts[$name] = [PSCredential]::new(('qa_'+$name),(ConvertTo-SecureString (New-RandomSecret) -AsPlainText -Force))
        }
        [pscustomobject]@{ Jwt=(ConvertTo-SecureString (New-RandomSecret) -AsPlainText -Force); Accounts=$accounts } | Export-Clixml -LiteralPath $secretPath
        @{ instance=[guid]::NewGuid().ToString('N'); ready=$false } | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8
        Invoke-QaEnvironment {
            $access = Get-PrivateAccess
            $payload = @{}
            foreach ($name in $access.Accounts.Keys) { $payload[$name]=@{username=$access.Accounts[$name].UserName;password=$access.Accounts[$name].GetNetworkCredential().Password} }
            $payload | ConvertTo-Json -Depth 5 -Compress | & $python tools/agroscan_qa.py init
            if ($LASTEXITCODE -ne 0) { throw 'Inicialización QA fallida; no se habilita el servidor.' }
        }
    }
    'start' {
        Invoke-QaEnvironment {
            & $python tools/agroscan_qa.py check
            if ($LASTEXITCODE -ne 0) { throw 'QA no válido.' }
            Assert-FreePort 8778; Assert-FreePort 5188
            $node = (Get-Command node.exe).Source
            $backend = Start-Process -FilePath $python -ArgumentList '-u','tools/agroscan_qa.py','serve' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $qa 'backend.log') -RedirectStandardError (Join-Path $qa 'backend-error.log')
            Save-ProcessRecord $backend 'backend'
            try {
                $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
                $healthy = $false
                for ($attempt=0; $attempt -lt 30; $attempt++) {
                    try { $health=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8778/api/health' -Headers @{'X-AgroScan-QA'=$manifest.instance} -TimeoutSec 2; if ($health.Headers['X-AgroScan-QA-ID'] -eq $manifest.instance) { $healthy=$true; break } } catch { Start-Sleep -Milliseconds 300 }
                }
                if (!$healthy) { throw 'Backend QA no respondió con la identidad correcta.' }
                $frontend=Start-Process -FilePath $node -ArgumentList 'node_modules/vite/bin/vite.js','--config','vite.qa.config.ts' -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $qa 'frontend.log') -RedirectStandardError (Join-Path $qa 'frontend-error.log')
                Save-ProcessRecord $frontend 'frontend'
                $webHealthy=$false
                for ($attempt=0; $attempt -lt 30; $attempt++) {
                    try { $web=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:5188/api/health' -TimeoutSec 2; if ($web.Headers['X-AgroScan-QA-ID'] -eq $manifest.instance) { $webHealthy=$true; break } } catch { Start-Sleep -Milliseconds 300 }
                }
                if (!$webHealthy) { throw 'Frontend no respondió con la identidad QA correcta.' }
                Write-Output 'QA disponible: http://127.0.0.1:5188 — datos y credenciales separados.'
            } catch { Stop-QaProcess 'frontend'; Stop-QaProcess 'backend'; throw }
        }
    }
    'stop' { Stop-QaProcess 'frontend'; Stop-QaProcess 'backend'; Write-Output 'Procesos QA detenidos; datos conservados.' }
    'status' { Invoke-QaEnvironment { & $python tools/agroscan_qa.py check; if ($LASTEXITCODE -ne 0) { throw 'Verificación QA fallida.' } } }
    'credentials' {
        $access = Get-PrivateAccess
        if ($Reveal -and !$Role) { throw 'Para revelar una contraseña, selecciona un único rol.' }
        if ($Reveal) { return [pscustomobject]@{ Username=$access.Accounts[$Role].UserName; Password=$access.Accounts[$Role].GetNetworkCredential().Password } }
        if ($Role) { return $access.Accounts[$Role] }
        $access.Accounts.Keys | Sort-Object | ForEach-Object { [pscustomobject]@{Role=$_; Username=$access.Accounts[$_].UserName} }
    }
    'verify' {
        Invoke-QaEnvironment {
            $access=Get-PrivateAccess; $payload=@{}
            foreach ($name in $access.Accounts.Keys) { $payload[$name]=@{username=$access.Accounts[$name].UserName;password=$access.Accounts[$name].GetNetworkCredential().Password} }
            $payload | ConvertTo-Json -Depth 5 -Compress | & node.exe --experimental-strip-types tools/agroscan_qa_verify.mjs
            if ($LASTEXITCODE -ne 0) { throw 'Verificación HTTP QA fallida.' }
            $payload | ConvertTo-Json -Depth 5 -Compress | & $python tools/agroscan_qa_verify.py
            if ($LASTEXITCODE -ne 0) { throw 'Compra DEMO o aislamiento en copia QA fallidos.' }
        }
    }
}
