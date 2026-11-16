# AG-046 / AGROP-54 — Incremento 03: Integridad de información

**Estado:** IMPLEMENTACIÓN DE PRUEBAS PREPARADA; **EJECUCIÓN LOCAL PENDIENTE**.

**Referencia:** `main` `1d3b66b7017f7f9139a5a35521f458bf100f6a66`, auditado el 16/11/2026. Los cambios locales del usuario y la rama `feature/AGROSCAN-demo-vercel` no se han inspeccionado ni modificado aquí.

## 1. Objetivo y límites

Validar la coherencia de registros del sistema, los archivos de imagen, hashes, respaldos y restauración, usando exclusivamente instancias de SQLite temporales, cuentas sintéticas y archivos de prueba. El **criterio de aprobación** es la observación del resultado real en un log de ejecución; la existencia del código no acredita el cumplimiento.

No usar `backend/data/agroscan.db`, fotografías de campo, dispositivos ESP32 ni la instalación operativa para esta batería. El funcionamiento tras detener y volver a iniciar el proceso FastAPI es responsabilidad de I04, no I03.

## 2. Evidencia implementada

| Control I01 | Prueba de I03 | Aceptación comprobable |
|---|---|---|
| INT-01 | `test_int01_llaves_foraneas_activas_por_conexion` | `PRAGMA foreign_keys = 1` en conexiones nuevas |
| INT-02 | `test_int02_integrity_check_sqlite_ok` | `PRAGMA integrity_check = ok` y `validate_database` |
| INT-03 | `test_int03_sin_fks_huerfanas_y_rechaza_una_nueva` | `foreign_key_check = []` y FK huérfana rechazada |
| INT-04 | `test_int04_*` (2 casos) | Relaciones, conteo, tamaño, hash del archivo; ausencia impide publicar respaldo |
| INT-05 | `test_int05_api_rechaza_archivo_vacio_mime_y_bytes_incorrectos` | HTTP 422 y cero capturas persistidas |
| INT-06 | `test_int06_fallo_de_publicacion_rollback_y_sin_huerfanos` | HTTP 500, no crea fila ni temporal residual y admite reintento |
| INT-07 | `test_int07_idempotency_key_no_duplica_original` | Mismo ID, una fila y bytes originales |
| INT-08 | `test_int08_sha_original_tamper_impide_decision_formal` | Archivo alterado con igual tamaño => HTTP 409 y cero revisiones |
| INT-09 | `test_int09_dos_imagenes_requieren_dos_decisiones` | Sigue pendiente tras primera imagen y se completa tras segunda |
| INT-10 | `test_int10_reporte_csv_sha256_estable_y_conteos` | CSV canónico repetible y SHA-256 reproducible |
| BKP-01 | `test_bkp01_zip_manifest_sqlite_imagenes_y_hashes` | ZIP contiene SQLite, imágenes, tamaños y hashes verificados |
| BKP-02 | `test_bkp02_*` (2 casos) | Imágenes alteradas / traversal ZIP rechazados |
| BKP-03 | `test_bkp03_restaura_ids_relaciones_revisiones_y_bytes` | Recuperación de vínculos, eventos, metadatos y bytes |
| BKP-04 | `test_bkp04_rollback_si_falla_sustitucion_final_de_imagenes` | Fallo inyectado en sustitución final no pierde estado pre-restauración |
| BKP-05 | `test_bkp05_alta_lote_debe_bloquearse_durante_restauracion` | Al suspender capturas, un `POST /api/lots` concurrente **debería** devolver HTTP 503 |

**Nota técnica INT-08:** el hash contra el que se contrasta la fotografía debe estar acreditado por un snapshot o decisión histórica. `images` no tiene un SHA-256 original almacenado como columna. No suponer que todas las fotografías históricas pueden auditarse retroactivamente contra un hash de captura.

**Nota técnica BKP-05:** `suspend_capture()` controla operaciones registradas por `capture_guard`; el endpoint `POST /api/lots` se inspeccionó sin esa dependencia. La prueba es una **aserción estricta** del comportamiento esperado. Si devuelve HTTP 201, el ejecutor registra `BRECHA_BKP05_CONFIRMADA` y finaliza con código distinto de cero. No cambiar la aserción a 201 para forzar una aprobación. Este test confirma únicamente ese endpoint y ese proceso; no implica que los demás endpoints o un despliegue multiproceso estén protegidos.

## 3. Regresiones reutilizadas

- `backend/tests/test_agrop52_image_recovery.py`: fallos y reintentos de almacenamiento.
- `backend/tests/test_agrop53_backup.py`: validaciones unitarias del respaldo.
- `backend/tests/test_agrop53_backup_integration.py`: flujo completo restaurar SQLite e imagen.
- `backend/tests/test_ag056_final_api.py`: revisión de dos fotografías, consistencia y control de revisión.
- `backend/tests/test_agrop48_piece_history.py`: trazabilidad y reproducibilidad del CSV.

No son pruebas físicas. El nuevo ejecutor las repite para detectar regresiones en el checkout local, independientemente del resultado anterior I02.

## 4. Ejecución y conservación de evidencias

Desde la raíz del repositorio:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\audit\ag046_i03_run.py
```

Si aparece `BRECHA_BKP05_CONFIRMADA` y el script retorna un error de proceso, **no es necesario repetirlo indefinidamente**: es un resultado de auditoría pendiente de corrección. Consultar siempre el archivo `AG046_I03_RESUMEN.md` del último `docs/ag046/runs/AG046_I03_*`.

El ejecutor guarda:

- `AG046_I03_RESUMEN.md` con etapas y estado.
- `AG046_I03_MATRIZ_RESULTADOS.csv` con INT-01 a INT-10, BKP-01 a BKP-05.
- `AG046_I03_RESULTADOS.json` con commit local, ambiente, conteos y código de salida.
- Siete logs de ejecución independientes.

**Estados separados:** `APROBADO` significa que una prueba alcanzó su aceptación; `BRECHA_BKP05_CONFIRMADA` significa que el requisito de protección concurrente **no** se alcanzó. La matriz I01 permanece intacta y puede actualizarse con las evidencias reales tras revisión.

## 5. Criterios para cierre del incremento

1. Las 16 nuevas pruebas estrictas y las cinco regresiones terminan aprobadas.
2. El control BKP-05 termina aprobado, **o queda documentado como defecto abierto con severidad, responsable y plan de corrección**. No declarar una restauración completamente segura mientras exista esa brecha.
3. Las evidencias se conservan con fecha, SHA local y resultado sin secretos.
4. Los riesgos fuera de alcance, incluidos `SEC-11`, `SEC-12`, reinicio real y multiproceso, permanecen explícitos.

## 6. Restricción de cambios

Este incremento **solo agrega pruebas, documentación y ejecutor**. No modifica firmware, frontend, autenticación, bases reales, controladores de operación ni archivos ya editados por otros desarrollos.
