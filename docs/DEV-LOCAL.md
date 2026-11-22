# Desarrollo local con sesión persistente

Desde la raíz del repositorio, iniciar primero FastAPI en una terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools/agroscan_dev.ps1" -Action backend
```

En otra terminal, iniciar Vite:

```powershell
npm --prefix frontend run dev
```

Abrir **http://localhost:5173/acceso**. Detener cada servicio con Ctrl+C en su terminal.

- Requiere el Python externo ya configurado en `Documents/AgroScan-Python-Probe`.
- Requiere la SQLite DEV existente en `Documents/AgroScan-Dev/data/agroscan.db`, revisión `a016sessions`, junto con `manifest.json` y `jwt.clixml`. Se verifican y reutilizan sin copiar QA, migrar, recrear usuarios ni generar credenciales. Si faltan, el arranque se detiene.
- La clave JWT propia permanece cifrada mediante DPAPI fuera de Git. Usar las cuentas ya existentes en DEV.
- El lanzador habilita explícitamente `AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP=true` solo en sus procesos locales. No cambia producción ni políticas globales de PowerShell. Google y SMTP reales permanecen deshabilitados; contratación exclusivamente DEMO.
- Vite usa `/api` por proxy a `127.0.0.1:8000`; no configurar `VITE_API_BASE_URL`. Ambos servicios verifican su identidad para evitar conexiones a otro backend/base.
- `npm run dev` selecciona `vite.dev.config.ts`: Vite añade `X-AgroScan-Dev` en el servidor, nunca desde React. No iniciar con `npx vite` sin esa configuración. Si el Vite anterior estaba abierto, reiniciarlo. Enviar solo Origin/Referer directamente al puerto 8000 no sustituye la identidad del proxy.
- **No alternar localhost y 127.0.0.1 en el navegador:** son hosts distintos para las cookies. QA sigue en `http://127.0.0.1:5188`, separado del host del desarrollo. Cookies HttpOnly/SameSite Strict, CSRF, restauración y revocación conservan AUTH-01. Producción sigue requiriendo HTTPS.
- Comprobar login, F5, reapertura en el mismo perfil, cambio de empresa y logout. No ejecutar el backend directamente sin las variables de aislamiento: el arranque predeterminado de FastAPI puede seleccionar la base histórica.

## YOLOE local en CPU

Con el backend DEV detenido, desde la raíz:

```powershell
& "$env:USERPROFILE\Documents\AgroScan-Python-Probe\Scripts\python.exe" -m pip install -r vision/requirements-dev-cpu.txt
& "$env:USERPROFILE\Documents\AgroScan-Python-Probe\Scripts\python.exe" -m pip check
```

El archivo reutiliza Ultralytics/CLIP del proyecto y fija Torch/Torchvision CPU y OpenCV compatible. Reiniciar la terminal backend con el comando anterior. No usar `backend\.venv`. Los pesos y prompts existentes se conservan; no se entrena ni modifica la configuración V2. La caché de Ultralytics queda en `Documents/AgroScan-Dev/runtime/ultralytics`, fuera de Git. La foto debe ser JPG/PNG, mínimo 128 px y máximo 2 MiB. Una respuesta técnica válida puede indicar varias frutas, confianza insuficiente o ausencia de detección; no acredita exactitud experimental.

## Calidad V2 y mediciones

DEV usa explícitamente `Documents/AgroScan-Dev/data/ag055_v2/models`. Deben existir `ag055_v2_mango.json`, `ag055_v2_tomate.json` y, en la carpeta padre, su `SHA256SUMS.json`. La recuperación instaló copias byte a byte de los artefactos existentes verificados en `docs/ag055/AG055_V2.md`; no reentrenó, sustituyó ni descargó modelos nuevos. Tras guardar dos vistas distintas, el panel consulta `/vision/quality/v2/status` y ejecuta `/v2/analyze`. Si previamente mostró «Clasificación no disponible», recargar o pulsar «Reintentar clasificación».

YOLOE determina producto/máscara; V2 genera propuestas E0/E1/E2 o «no evaluable». El resultado permanece preliminar: no cambia automáticamente el dictamen humano ni confirma adquisición sin pesos. La geometría sin calibración se muestra en píxeles. Ver marcadores en una foto no acredita plano, impresión, cámara fija ni dimensiones físicas; no confirmar esas condiciones sin evidencia real.
