# Ejecutar exclusivamente desde el worktree security/devsecops-hardening.
# Este script modifica package.json / package-lock.json con npm (no edita hashes a mano).
# -AllowMinimatchMajorOverride fuerza temporalmente minimatch 11.x y exige QA completa.
[CmdletBinding()]
param([switch]$AllowMinimatchMajorOverride)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location (Join-Path $repo 'frontend')
try {
    $branch = git branch --show-current
    if ($LASTEXITCODE -ne 0 -or $branch -ne 'security/devsecops-hardening') {
        throw 'Debes ejecutar este script solo en la rama security/devsecops-hardening.'
    }
    Write-Host 'Actualizando avisos compatibles mediante npm audit fix (sin --force)...'
    npm audit fix --package-lock-only --ignore-scripts
    # npm audit fix puede devolver 1 si queda un aviso no corregible sin major.
    if ($LASTEXITCODE -gt 1) { throw 'npm audit fix falló por un problema operativo.' }
    if ($AllowMinimatchMajorOverride) {
        Write-Warning 'minimatch cambia de versión mayor (10 -> 11). Se deben revisar ESLint y pruebas.'
        npm pkg set 'overrides.minimatch=^11.0.1'
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo establecer override.' }
        npm install --package-lock-only --ignore-scripts
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el lockfile con el override.' }
    }
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci falló.' }
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw 'ESLint falló.' }
    npm test
    if ($LASTEXITCODE -ne 0) { throw 'Tests frontend fallaron.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'El build frontend falló.' }
    npm audit --audit-level=moderate
    if ($LASTEXITCODE -ne 0) {
        throw 'Quedan avisos npm moderate o superior. Revisar npm audit antes de commit.'
    }
    Write-Host 'Dependencias npm actualizadas y sin alertas >= moderate en esta ejecución.'
    Write-Host 'Revisa git diff -- frontend/package.json frontend/package-lock.json antes de añadir al commit.'
}
finally { Pop-Location }
