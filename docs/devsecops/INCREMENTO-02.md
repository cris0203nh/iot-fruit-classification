# AgroScan — Incremento 02: remediación y endurecimiento

**Rama de trabajo exclusiva:** `security/devsecops-hardening`. **Sin merge a `main`.**
**Línea base:** `docs/devsecops/BASELINE-01.json` (ejecución de Actions `ce9a16d`).

## Controles implementados

| Control | Antes | Después esperado y verificación |
|---|---|---|
| IoT POST `/api/iot/measurements` | No autentica emisor | Clave independiente para cada `device_id` enviada en `X-Device-Key`; verificación por comparación de tiempo constante; 401 ante ausencia/error, 503 si la configuración no existe; sin escritura no autorizada. |
| IoT GET `/api/iot/status` | Acceso anónimo | Requiere JWT de usuario activo con rol permitido (administrador/revisor/operador); conserva el mismo formato para React autenticado. |
| Puente serial/HTTP y simulador | Envíos sin credencial | Lee `AGROSCAN_IOT_DEVICE_KEY` del entorno, nunca de argumentos CLI; HTTP solo a loopback, HTTPS en destinos remotos; conserva retries e idempotencia. |
| Login | Sin límite de intentos | Limitador en memoria por IP + cuenta (5 errores / 5 minutos) y por IP total (20 errores / 5 minutos), HTTP 429 y `Retry-After`. No confía en `X-Forwarded-For` arbitrario. |
| Python SCA | `opentelemetry-api==1.45.0` | Pin `==1.45.1` para CVE-2026-114603. Nuevo gate `pip-audit` de hallazgos de paquetes declarados. |
| Bandit | Solo observación | Bloqueo en hallazgos HIGH o superiores. Se mantienen B105/B311 LOW para revisión; no se deshabilitan reglas. |
| npm audit | 11 registros (1 alta, 10 moderadas) | **Pendiente de lockfile regenerado con npm conectado al registry** y verificación real de ESLint/test/build/audit. No se presenta como corregido en el parche base. |

## Configuración necesaria (sin insertar secretos en Git)

Backend: `AGROSCAN_IOT_KEYS_JSON` debe ser un objeto JSON con clave `device_id` y valor secreto aleatorio individual de **al menos 32 caracteres**. El `device_id` debe ser el exacto emitido por ESP32, por ejemplo `esp32-<MAC>` o `simulator-esp32-<MAC>`. Cada entrada debe tener una clave distinta. Se puede guardar en `backend/.env` **solo local, excluido por `.gitignore`**, o en variables de entorno del servicio. No enviar ese archivo por chat, commits o evidencias.

Puente/PC: la variable `AGROSCAN_IOT_DEVICE_KEY` debe contener exclusivamente la clave del dispositivo correspondiente. Por ejemplo, desde PowerShell (el secreto se debe generar y distribuir por un canal seguro):

```powershell
# Generar un valor y resguardarlo fuera del repositorio.
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Establecer AGROSCAN_IOT_KEYS_JSON en el backend y AGROSCAN_IOT_DEVICE_KEY
# en el equipo del puente usando el mismo valor asignado a su device_id.
python firmware/tools/serial_bridge.py --port COM3 --url http://127.0.0.1:8000/api/iot/measurements
```

Sin las variables, **la publicación falla de forma segura** (503/cliente rechazado). El frontend requiere sesión del operador para consultar el estado. La autenticación solo acredita el **puente/PC con su clave**, NO que el sensor físico sea confiable ni que esté calibrado. USB físico, almacenamiento de tokens, rotación, revocación, TLS del servidor, proxies y control de acceso a la estación siguen bajo responsabilidad de despliegue.

## Login y despliegue

El limitador de login es **por proceso** y utiliza `request.client.host`. Sirve en desarrollo o un proceso de backend, pero para múltiples workers/réplicas se requiere un backend compartido (Redis, gateway o WAF). Si hay reverse proxy, configurar proxies confiables, HTTPS y límites en el proxy; no confiar ciegamente en cabeceras proporcionadas por el usuario. Limitar también tamaño de body y usar controles de infraestructura, monitoreo y bloqueo por cuenta si se despliega públicamente.

## Remediar las dependencias npm en Windows

En tu **worktree DevSecOps** con acceso al registro npm:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\devsecops\remediar-npm.ps1
```

El script utiliza `npm audit fix --package-lock-only` (sin `--force`) y después ejecuta `npm ci`, lint, test, build y audit. Si continúa `minimatch` vulnerable, la variante experimental agrega un `overrides.minimatch` mayor (11.x) y **solo se aceptará si pasan todos los controles**:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\devsecops\remediar-npm.ps1 -AllowMinimatchMajorOverride
```

No forzar una versión mayor en producción sin revisar las API que utilizan los paquetes padres. No registrar un `package-lock.json` editado manualmente. Si el script falla, revisar con `git diff` y diagnosticar el árbol; no realizar commit de un lock inconsistente. Una vez corregido npm y confirmado `npm audit` sin alertas (>= moderate), se podrá habilitar el gate de npm en el siguiente ajuste de CI.

## Verificación del incremento (desde la raíz; Python 3.12 y deps instaladas)

```powershell
$env:AGROSCAN_JWT_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:PYTHONPATH = "backend"
python -m unittest discover -s backend/tests -p 'test_*.py' -v
python -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s scripts/devsecops -p 'test_*.py' -v
npm ci --prefix frontend
npm run lint --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
```

Pruebas negativas incluidas: POST sin clave / clave errónea / clave de otro dispositivo / backend sin configuración; GET sin JWT; login con 5 intentos fallidos, cuenta inexistente y evasión por múltiples usuarios; pruebas de puente y simulador con clave de entorno, URL HTTP remota rechazada y reintentos idempotentes.

## Línea base y tabla antes/después

| Métrica | Antes (`ce9a16d`) | Después del patch, **no verificado en Actions** |
|---|---|---|
| Bandit LOW | 2 | Repetir escaneo; excepciones por contexto justificadas |
| npm audit | 1 HIGH + 10 MODERATE | Pendiente de regenerar lockfile y escaneo |
| pip-audit backend | 1 (OpenTelemetry) | Esperado 0 para pin actualizado; verificar en runner |
| Gitleaks histórico | 3 fixtures de test | Historial permanece; documentar sin rebajar el gate nuevo |
| Gitleaks nuevos | 0 | Esperado 0; verificar en runner |
| POST IoT sin credencial | 200 | 401/503, sin persistencia (prueba añadida) |
| GET estado sin JWT | 200 | 401 (prueba añadida) |
| Login fuerza bruta | No limitado | HTTP 429 (prueba añadida) |

**No asumir** que Gitleaks o un escáner en verde garantizan ausencia de riesgos. El `backend/.env`, las BD e imágenes locales **no** deben incluirse en el parche o commit. No alteramos firmware ESP32 ni APIs de evaluación: el dispositivo sigue comunicando JSON por serial y su identidad debe probarse aparte.
