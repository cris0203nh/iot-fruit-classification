# AgroScan DevSecOps — Incremento 03: DAST para FastAPI

**Rama:** `security/devsecops-hardening`
**Base de trabajo:** commit `8146ad2` (Incrementos 01–02 y ajuste de CI).
**Objetivo:** complementar SAST/SCA/secret scanning con pruebas dinámicas de la API en un entorno aislado.

## Alcance y medidas de seguridad

- Nuevo job `DAST API ZAP (pasivo, gate alta/crítica)` en el workflow existente.
- Se importa el OpenAPI de FastAPI con `zap-api-scan.py -f openapi -S`, **modo seguro, sin active scan**. No se ejecuta `zap-full-scan.py` ni se prueban aplicaciones externas.
- La API escucha solo en `127.0.0.1:8765` en el runner `ubuntu-24.04`; el contenedor usa `--network host` únicamente para alcanzar ese servicio local.
- En una carpeta temporal (`mktemp`) se copia **solamente** `backend/app`. `backend/.env`, `backend/data`, archivos de usuarios e imágenes reales no se copian.
- Se crea SQLite vacía con `Base.metadata.create_all`. JWT y clave del puente IoT son aleatorios y efímeros; la clave IoT no se transmite al escáner.
- Preflight HTTP de solo lectura y comprobaciones de acceso denegado: `/api/health` y `/openapi.json` -> 200; `/api/iot/status`, `/api/auth/me`, `/api/users` -> 401; POST IoT sin clave -> 401 y **sin escribir una medición**.
- El proceso Uvicorn y el directorio temporal se eliminan al terminar el job. El archivo crudo de ZAP se elimina siempre, incluido el caso de error.

## Integración y controles

- Contenedor ZAP **fijado por digest** a una imagen oficial ZAP 2.17.0 de GHCR. Antes de actualizarlo, verificar el digest de la nueva versión y repetir el pipeline.
- Se procesa el JSON tradicional generado por ZAP. `scripts/devsecops/normalize_zap.py` exporta solamente identificador numérico de regla, severidad, conteo y número agregado de ocurrencias; **no exporta URLs, headers, cuerpos de respuesta, evidencias ni tokens**.
- Exit status de ZAP 0/1/2 indica escaneo procesable (éxito, fallo por regla, advertencias); 3 u otro estado se trata como **error operativo**, nunca como éxito.
- El nuevo gate bloquea alertas **HIGH o CRITICAL**. LOW y MEDIUM se registran en observación mientras se clasifican. Un reporte vacío, inválido o ausente falla cerrado.
- Artefacto: `devsecops-zap-dast` con archivo `reports/zap.json` (14 días).
- No se cambia la semántica de las rutas de la aplicación ni se fusiona la rama con `main`.

## Lo que NO prueba este incremento

- No ejecuta exploración autenticada ni verificación de acceso cruzado entre usuarios/roles mediante ZAP; las pruebas unitarias existentes sí validan controles funcionales de roles y JWT.
- No prueba ataques activos como SQLi, XSS, fuzzing o modificación masiva de registros. Podrán planificarse después, solo sobre un entorno explícitamente desechable y con alcance autorizado.
- No valida la identidad física del ESP32 ni la seguridad del enlace USB.
- El escaneo pasivo reporta **señales**, no vulnerabilidades explotables confirmadas. La interpretación requiere triaje.

## Validación local de los scripts

Desde la raíz del worktree DevSecOps en PowerShell:

```powershell
& .\backend\.venv\Scripts\python.exe -m unittest discover -s scripts/devsecops -p "test_*.py" -v
git diff --check
git status --short
```

En GitHub Actions revisar los **7 jobs** y el nuevo artefacto `devsecops-zap-dast`. Si el job DAST falla, revisar el error de inicialización, red o el reporte sanitizado y **no deshabilitar el gate ni publicar el reporte crudo**.

## Referencias técnicas

- OWASP ZAP, [API Scan](https://www.zaproxy.org/docs/docker/api-scan/) (opción `-S`).
- OWASP ZAP, [ZAP Docker User Guide](https://www.zaproxy.org/docs/docker/about/).
- OWASP ZAP, [guía de seguridad de escaneos](https://www.zaproxy.org/faq/is-there-any-danger-when-scanning-with-zap-against-a-live-website-e-g-create-delete-update-corrupt-data/).
