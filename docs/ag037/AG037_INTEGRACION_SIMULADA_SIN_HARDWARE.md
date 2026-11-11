# AG-037 / AGROP-45 — Validación integral sin hardware físico

## Alcance

Prueba de integración reproducible **en SQLite temporal**, utilizando endpoints reales de FastAPI. Solo se simulan los dos registros que normalmente remite el ESP32 y la predicción que normalmente devuelve YOLOE. **No se modifica el sistema para saltarse validaciones, ni se toca `backend/data/agroscan.db`.**

El objetivo de AG-037 sigue siendo: resultados inciertos pendientes de revisión, resolución autorizada, y conservación de la evidencia y de la respuesta automática original. Las clases E0/E1/E2 solo pueden surgir de una decisión humana registrada, no del detector de objetos.

## Pruebas incluidas

Archivo: `backend/tests/test_agrop45_flujo_integral_simulado.py`.

- Alta de una evaluación de mango y dos mediciones **simuladas** de una misma sesión, con estabilidad, tara, calibración, secuencia y timestamps válidos.
- Subida real por HTTP (`multipart/form-data`) de JPEG generado localmente, con clave de idempotencia.
- Confirmación de asociación de fotografía y dos pesajes a través del endpoint existente.
- Aplicación de la compuerta de incertidumbre con detección de baja confianza controlada, transición `processing → pending_review`.
- Filtro de pendientes, prohibición de que el operador resuelva, resolución humana simulada autenticada como revisor, lectura posterior de la imagen y snapshot automático.
- Nuevo acceso directo a la base SQLite desde una conexión distinta para verificar persistencia de eventos y SHA256.
- Caso `no_evaluable` sin inventar E0/E1/E2, detector no disponible y caso confiable sin autoetiquetado de calidad.
- Rechazo del pesaje inestable, rechazo de adquisición sin pesajes y reintento idempotente de subida.

## Ejecutar en PowerShell desde la raíz del repositorio

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
Push-Location backend
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_agrop45_flujo_integral_simulado.py' -v
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'Falló integración simulada AG-037' }
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'Falló regresión del backend' }
Pop-Location
npm --prefix frontend test
npm --prefix frontend run build
```

Para guardar evidencia de consola sin confundirla con evaluación física:

```powershell
$evidencia = Join-Path $env:USERPROFILE 'Documents\AgroScan_AG037_Evidencia_Simulada'
New-Item -ItemType Directory -Force -Path $evidencia | Out-Null
Push-Location backend
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_agrop45_flujo_integral_simulado.py' -v *>&1 |
  Tee-Object -FilePath (Join-Path $evidencia 'integracion_simulada_consola.txt')
$testExit = $LASTEXITCODE
Pop-Location
if ($testExit -ne 0) { throw 'El informe incluye errores; no declarar aprobado' }
```

## Restricciones y evidencia correcta en Jira

- El sensor ESP32 **NO fue probado físicamente**: dos filas de `Measurement` reproducen su protocolo para ejercitar los validadores auténticos.
- No se miden falsos positivos, IoU ni exactitud del detector: `_infer` se sustituye en test por resultados definidos y claramente simulados.
- La prueba no inserta piezas en la base habitual ni crea una sesión visible en el navegador conectado al backend habitual. Para evidenciar la UI deben utilizarse capturas de una sesión de prueba autorizada, no atribuirle a esta suite una captura real.
- El umbral actual de detección es 0,40. El sustento experimental y el análisis de falsos positivos sobre la muestra aceptada corresponden al **bloque experimental de AG-037**; esta prueba de integración no calibra umbrales.
- No subir a Git imágenes, `.db`, `.env`, tokens ni los ZIP privados de fotografías.

## Estado del cierre

La suite acredita la integración simulada cuando muestra `OK`; la prueba de hardware físico y la evaluación experimental del umbral quedan diferenciadas. No marcar la historia como completada únicamente por aprobar esta suite.
