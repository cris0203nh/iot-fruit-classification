# AG-034: monitor auxiliar del Working Set residente de un proceso de perfilado.
# Solo Windows PowerShell. No valida cámara, ESP32, etiquetas ni hardware definitivo.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Zip,
    [Parameter(Mandatory=$true)][string]$Salida,
    [int]$IntervaloMs = 100
)
$ErrorActionPreference = 'Stop'
if ($IntervaloMs -lt 20 -or $IntervaloMs -gt 1000) {
    throw 'IntervaloMs debe estar entre 20 y 1000 ms.'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "No existe Python: $Python" }
if (-not (Test-Path -LiteralPath $Zip -PathType Leaf)) { throw "No existe ZIP: $Zip" }
if (Test-Path -LiteralPath $Salida) { throw "No sobrescribir carpeta existente: $Salida" }
New-Item -ItemType Directory -Path $Salida -Force | Out-Null
$programa = 'vision.evaluation.agrop42.perfil_recursos_ag034'
$benchmark = Join-Path $Salida 'benchmark'
$out = Join-Path $Salida 'consola_out.txt'
$err = Join-Path $Salida 'consola_error.txt'
# Start-Process requiere comillas explícitas para parámetros de ruta con espacios.
$argumentos = '-m {0} --zip "{1}" --salida "{2}" --repeticiones 7 --bucles 500 --repeticiones-pipeline 3' -f `
    $programa, $Zip.Replace('"',''), $benchmark.Replace('"','')
$proceso = Start-Process -FilePath $Python -ArgumentList $argumentos -PassThru `
    -WorkingDirectory (Get-Location).Path -RedirectStandardOutput $out -RedirectStandardError $err
$inicio = [System.Diagnostics.Stopwatch]::StartNew()
$muestras = New-Object System.Collections.ArrayList
try {
    do {
        $proceso.Refresh()
        if (-not $proceso.HasExited) {
            try {
                $activo = Get-Process -Id $proceso.Id -ErrorAction Stop
                [void]$muestras.Add([PSCustomObject]@{
                    elapsed_ms = [math]::Round($inicio.Elapsed.TotalMilliseconds, 2)
                    working_set_mib = [math]::Round($activo.WorkingSet64 / 1MB, 3)
                    pid = $proceso.Id
                })
            } catch [Microsoft.PowerShell.Commands.ProcessCommandException] { }
            Start-Sleep -Milliseconds $IntervaloMs
        }
    } while (-not $proceso.HasExited)
    $proceso.WaitForExit()
} finally { $inicio.Stop() }
$muestras | Export-Csv -Path (Join-Path $Salida 'muestras_rss.csv') -NoTypeInformation -Encoding UTF8
$max = $null
if ($muestras.Count -gt 0) {
    $max = ($muestras | Measure-Object -Property working_set_mib -Maximum).Maximum
}
$reporte = [ordered]@{
    estado = 'medicion_local_no_hardware_acreditado'
    exit_code_benchmark = $proceso.ExitCode
    duration_ms = [math]::Round($inicio.Elapsed.TotalMilliseconds, 2)
    max_rss_mib_muestreado = $max
    numero_muestras = $muestras.Count
    intervalo_muestreo_ms = $IntervaloMs
    alcance = 'Solo proceso Python del benchmark; no RAM total del equipo, proceso FastAPI ni GPU'
    umbrales_de_aceptacion_acreditados = $false
    clasificacion_e0_e1_e2_evaluada = $false
    cierre_total_AG034_acreditado = $false
}
$reporte | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $Salida 'AG034_RSS_resultado.json') -Encoding UTF8
$reporte | ConvertTo-Json -Depth 5
if ($proceso.ExitCode -ne 0) { throw "El benchmark terminó con código $($proceso.ExitCode). Consulta consola_error.txt" }
