# AG-038 / AGROP-46 — Incremento 02: auditoría y evidencia de decisión

## Propósito y criterios de Jira

Historia: «Como revisor, quiero confirmar o corregir un resultado dejando justificación».

Criterios: **valor original, nuevo valor, autor, fecha, motivo y evidencia íntegra**. AG-027 y AG-037 son dependencias ya implementadas y no se reimplementan.

Este incremento no cambia endpoints ni tablas; utiliza las implementaciones ya integradas en AG-038 Incremento 01. Añade una auditoría determinista de decisiones **simuladas** en FastAPI y SQLite temporal, más validación de regresión y salidas reproducibles para Jira.

## Flujo comprobado

| Escenario de integración | Valor original | Acción | Anterior → nuevo | Esperado |
|---|---|---|---|---|
| A — confirmar | E1 sintético | `confirm` | E1 → E1 | Evento sin modificación |
| A — corregir | E1 sintético | `correct` | E1 → E2 | Histórico original E1 preservado |
| A — confirmar corrección | E1 sintético | `confirm` | E2 → E2 | Evento adicional |
| B — primera etiqueta | sin categoría | `initial_label` | nulo → E0 | No atribuir grado a YOLOE |
| B — sin dictamen | sin categoría | `no_evaluable` | E0 → no_evaluable | Revisión sin grado |
| B — reevaluar | sin categoría | `correct` | no_evaluable → E1 | Recuperación trazable |
| A — reintento exacto | E1 sintético | `confirm` | E2 → E2 | Mismo ID si se repite UUID |

Comprobaciones negativas: operador HTTP 403; revisión obsoleta HTTP 409; motivo inválido HTTP 422; imagen ajena HTTP 404. El auditor prueba integridad SHA256 y persistencia en segunda conexión SQLite.

## Evidencia generada

Ejecutar desde `backend/`:

```powershell
$salida = "$env:USERPROFILE\Documents\AgroScan_AG038_Auditoria_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
& '.\.venv\Scripts\python.exe' -m audit.ag038_cierre --salida $salida
```

Genera en la carpeta nueva:
- `resumen_auditoria.json`: resultados de la ejecución y comprobaciones.
- `bitacora_decisiones.csv`: eventos con valor original, anterior/nuevo, responsable, fecha, motivo, imagen y SHA256.
- `informe_auditoria.md`: interpretación y limitaciones.

La salida se crea **fuera del repositorio** para no publicar accidentalmente datos de evidencia o pruebas. No se sobrescribe una carpeta existente. La SQLite temporal y la imagen sintética se eliminan automáticamente.

Pruebas:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_agrop46_cierre_auditoria.py' -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -q
```

Las pruebas de interfaz React y compilación se ejecutan desde la raíz con `npm --prefix frontend test`, `node --experimental-strip-types --test frontend/tests/agrop46-decisions.test.mjs` y `npm --prefix frontend run build`.

## Alcance, separación de evidencia y cierre

- La prueba utiliza **dos evaluaciones y una imagen JPEG sintéticas**, roles de prueba y SQLite temporal. No hay fruta, dictamen agronómico ni ESP32 físico.
- Las fechas y eventos exportados provienen de una ejecución real del software en la base aislada, no de un registro de producción.
- El resultado de YOLOE es detección, nunca predicción E0/E1/E2. El valor E1 original del escenario A es una **semilla sintética**, no un resultado automático del modelo.
- El panel React está desarrollado; falta una captura genuina de la pantalla de prueba si Jira exige evidencia visual. No generar ni atribuir capturas no obtenidas.
- No exponer `.db` operativa, claves, tokens, imágenes privadas ni credenciales en GitHub/Jira.
- Los endpoints heredados `/reviews` y `/vision/resolve` conservan las evidencias previas de AG-037. Las decisiones nuevas y enriquecidas usan `/review-decisions`; esta auditoría solo acredita las nuevas.
- La migración `b38c99a10246` debe comprobarse en el equipo antes de cualquier prueba sobre la base habitual. Ejecutar respaldo previo con FastAPI detenido si no se aplicó.

**Cierre técnico:** apto para solicitar aceptación del Sprint 11 tras ejecutar el auditor y pruebas en el equipo, revisar la bitácora generada y adjuntar las capturas auténticas de la interfaz. No confundir con validación de hardware real ni resultados de calidad del modelo.
