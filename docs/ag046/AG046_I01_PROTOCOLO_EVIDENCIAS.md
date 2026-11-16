# AG-046 — Protocolo de captura de evidencias (I02-I05)

Este documento define cómo obtener evidencia posteriormente. **No representa ejecuciones completadas.**

## Preparación segura

1. Usar rama separada (`feature/AGROP-54-...`), `git status --short` y registrar SHA de HEAD.
2. Usar backend con JWT **de pruebas**, SQLite temporal y fotografías sintéticas o autorizadas. No editar ni borrar los datos de `backend/data/agroscan.db` del usuario.
3. No anexar secretos ni tokens a logs, capturas o commits. No subir bases de datos reales ni backups completos públicos.
4. Ejecutar desde la raíz del repositorio PowerShell (Windows):

```powershell
git rev-parse HEAD
git status --short
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_agrop47_*.py" -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_agrop53_*.py" -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_agrop52_*.py" -v
```

Si las pruebas necesitan JWT, configurar **únicamente un secreto temporal de >=32 caracteres** mediante el mecanismo local ya documentado por `backend/app/security.py` (sin guardar la clave en evidencia). Registrar errores de entorno explícitamente; no declararlos tests aprobados.

## Para I02

- Preparar usuarios sintéticos administrador, revisor y operador.
- Validar no token, expiración, usuario inactivo, permisos de lectura/escritura y protección de API de respaldos.
- Por cada llamada almacenar método, ruta, código HTTP, cuerpo **depurado** y cambios observados en SQLite.

## Para I03

- Reproducir pruebas en directorio temporal con una DB inicial y dos imágenes por expediente.
- Obtener manifest de archivos y SHA-256 de cada archivo antes/después de crear backup, restaurar y probar fallo/rollback.
- Recopilar `PRAGMA integrity_check` y `PRAGMA foreign_key_check` sobre copia, sin escritura destructiva a DB personal.
- Forzar fallos de ZIP y escritura solo en almacenamiento temporal.

## Para I04

- Registrar PID del proceso FastAPI y sello de tiempo, crear expediente de prueba y capturar una instantánea JSON (lote, evaluación, dos imágenes, revisiones, estados y hashes).
- Detener **ese proceso** de forma controlada, iniciarlo de nuevo, registrar nuevo PID y comparar datos de respuesta, SHA y relaciones.
- Obtener una captura del historial y otra de la consulta de imágenes, con identificadores sintéticos.
- Los `TestClient` en memoria no sustituyen reiniciar el proceso real.

## Convención de evidencia

`docs/ag046/evidencias/AAAAMMDD_HHMMSS/<control_id>_<descripcion>.txt` para resúmenes sanitizados versionables. Datos sensibles, imágenes y respaldos completos deben permanecer en una ruta local **no versionada**. Documentar en el checklist la ubicación privada sin hacer públicos contenidos o credenciales.

## Estados permitidos

`PENDIENTE`, `APROBADO`, `FALLIDO`, `BLOQUEADO`, `NO_APLICA_JUSTIFICADO`. Conservar evidencia de una prueba fallida tanto como de una aprobada; ninguna prueba es aprobada por un `exit code` ajeno a su caso.
