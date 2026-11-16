# AgroScan — I05, ejecutar y auditar

Requisito: ejecutar desde la raíz `iot-fruit-classification`, con Python de `backend/.venv`, Node y dependencias de frontend ya instaladas.

## Instalación protegida

Descarga `AGROSCAN_I05_INSTALAR.py` y ejecuta:

```powershell
cd "C:\Users\Luigi\Documents\Proyectos Personales\iot-fruit-classification"
$kit = "$env:USERPROFILE\Downloads\AGROSCAN_I05_INSTALAR.py"
.\backend\.venv\Scripts\python.exe $kit --check
if ($LASTEXITCODE -ne 0) { throw 'Prevalidación I05 fallida' }
.\backend\.venv\Scripts\python.exe $kit --apply
if ($LASTEXITCODE -ne 0) { throw 'Instalación I05 fallida' }
.\backend\.venv\Scripts\python.exe $kit --verify
if ($LASTEXITCODE -ne 0) { throw 'Verificación I05 fallida' }
```

Instala **solo** una suite de pruebas transversal, un runner reproducible y dos documentos. No cambia el código de producción ni hace operaciones sobre SQLite o modelos.

## Validación

```powershell
.\backend\.venv\Scripts\python.exe .\tools\agroscan_i05_validate.py --preflight
if ($LASTEXITCODE -ne 0) { throw 'Faltan componentes I01–I04 o herramientas' }
.\backend\.venv\Scripts\python.exe .\tools\agroscan_i05_validate.py --run --evaluation E-000019
if ($LASTEXITCODE -ne 0) { Write-Warning 'Alguna etapa falló: revisar el informe generado.' }
```

El runner ejecuta: ESLint completo, build, `npm test`, pruebas I01–I05, pruebas unitarias backend I03 y `git diff --check`. Genera **un directorio nuevo** bajo `docs/agroscan-i05/runs/` con:

- `AGROSCAN_I05_CIERRE_TECNICO.md`
- `AGROSCAN_I05_RESULTADOS.json`
- logs individuales por etapa

Consulta el directorio real informado en la consola y adjunta el informe y logs que fallen. El hash SQLite pre/post detecta modificaciones no esperadas. La auditoría de base es solo de lectura; puede ser omitida si no existe o si SQLite está inaccesible.

## Qué no se puede declarar aprobado aún

El runner no manipula firmware ni un sensor real, no certifica desempeño independiente de V2, no acredita centímetros reales ni realiza interacciones de navegador. Las pruebas del runner son de regresión, no sustituyen la inspección manual o ensayos de campo.

**Criterio de cierre:** `--run` con todas las etapas `passed`, seguido de comprobación manual de resultados por historial. El alcance físico y metrológico queda expresamente pendiente si no se aporta evidencia.
