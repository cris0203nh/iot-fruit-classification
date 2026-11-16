# AgroScan — demo temporal sin costo (Vercel + FastAPI local)

## Alcance y seguridad

- Vercel aloja exclusivamente `frontend/` (React SPA). FastAPI, YOLOE, SQLite y fotos permanecen **en el PC**.
- Un Cloudflare Quick Tunnel publica de forma temporal el puerto **8787**, no el 8000: la pasarela bloquea `POST /api/iot/measurements`, `/api/admin/*`, `/docs`, `/openapi.json` y cualquier ruta no permitida.
- El enlace `https://...trycloudflare.com` es **público** y cambia cuando reinicias el túnel. La pasarela reduce exposición, pero **no garantiza privacidad absoluta ni reemplaza el inicio de sesión o un firewall**. No poner datos personales o credenciales de producción en una demo pública. Usar cuentas de prueba con permisos mínimos.
- La pasarela no modifica los originales. Las operaciones permitidas se realizan sobre una copia de `backend/data/agroscan.db` y de `backend/data/images`, creada en `.agroscan_demo/data/`. Los modelos originales **se leen**, no se copian ni se modifican.
- No publicar/registrar fotos reales sensibles ni credenciales; no colocar ningún secreto en variables `VITE_*`, pues se incluyen en el JavaScript público.
- El equipo debe estar encendido; detener `cloudflared`, pasarela y FastAPI al acabar. No usar para producción.

## Paso 0 — Antes de empezar

Instalar `cloudflared` para Windows desde la página oficial de Cloudflare; usar el binario `cloudflared.exe`. Verificar `cloudflared --version`. Se necesita Node/npm y el Python del `backend/.venv` ya configurado, y modelos locales disponibles.

Crear el proyecto en Vercel desde GitHub, seleccionando la rama que contiene el cambio de demo (si no está fusionada en `main`, elegir la rama correspondiente), y ajustar:

- Root Directory: **frontend**
- Framework Preset: **Vite**
- Build Command: `npm run build`
- Output Directory: `dist`
- Install Command: `npm ci` (si existe `package-lock.json`; en otro caso `npm install`)
- La variable `VITE_API_BASE_URL` se establecerá al obtener el túnel temporal, y el frontend debe volver a desplegarse después de modificarla. Las peticiones HTTPS remotas tienen un límite de espera de 30 segundos (8 segundos para desarrollo local).
- La regla SPA está en `frontend/vercel.json`; las rutas de React Router retornan `/index.html`.

## Paso 1 — Crear copia de datos SIN sobrescribir originales

Ejecutar desde la raíz del proyecto:

```powershell
.\backend\.venv\Scripts\python.exe .\tools\agroscan_demo_prepare.py --check
.\backend\.venv\Scripts\python.exe .\tools\agroscan_demo_prepare.py --create
```

La segunda ejecución no sobrescribe una copia ya creada. Si deseas reconstruirla, conserva o renombra la anterior manualmente tras detener la demo. La preparación no cambia `backend/data/`.

## Paso 2 — Arrancar FastAPI (terminal 1)

Configura **tu URL exacta de Vercel** (sin slash final). Es un origen, no una URL de API:

```powershell
.\tools\agroscan_demo_backend.ps1 -VercelOrigin 'https://TU-PROYECTO.vercel.app'
```

Si PowerShell restringe scripts, ejecuta `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\agroscan_demo_backend.ps1 -VercelOrigin 'https://TU-PROYECTO.vercel.app'`.

Comprobar en otro terminal: `Invoke-RestMethod http://127.0.0.1:8000/api/health`.

## Paso 3 — Arrancar pasarela local (terminal 2)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\agroscan_demo_gateway.ps1 -VercelOrigin 'https://TU-PROYECTO.vercel.app'
```

Comprobar: `Invoke-RestMethod http://127.0.0.1:8787/api/health`. Las rutas `/api/admin/backups` y `/api/iot/measurements` responderán 403.

## Paso 4 — Crear túnel temporal (terminal 3)

```powershell
cloudflared tunnel --url http://127.0.0.1:8787
```

Cloudflare imprimirá una dirección como `https://xxxx.trycloudflare.com`. NO cerrar la ventana. No añadir `/api` al valor de `VITE_API_BASE_URL`.

## Paso 5 — Conectar Vercel

En Vercel > Project > Settings > Environment Variables:

- Name: `VITE_API_BASE_URL`
- Value: `https://xxxx.trycloudflare.com`
- Environment: **Production** (y Preview si vas a usar esa URL)

Guardar y ejecutar **Redeploy** en la misma rama/commit con la variable nueva. La variable se incrusta en la compilación; **si el túnel cambia de URL, se requiere actualizarla y volver a desplegar**.

## Paso 6 — Ensayo académico

Abrir URL de Vercel, comprobar API "en línea" e iniciar sesión con una cuenta **de demostración** de privilegios mínimos. El token JWT vive en memoria y la API demo usa una clave JWT efímera generada para cada arranque, independiente de backend/.env. Revisar una evaluación, historial y trazabilidad. Si hace falta probar captura, los archivos y operaciones se guardan solamente en `.agroscan_demo/data/`.

El navegador solicita acceso a la cámara local de cada visitante. La cámara y la balanza física NO se transfieren mágicamente desde tu computadora: el puente de pesaje IoT sigue siendo local y la pasarela bloquea **la escritura IoT desde internet**. Si necesitas mostrar valores reales de la balanza, mantén el puente escribiendo directamente en `127.0.0.1:8000` en la computadora de la estación, nunca a través del túnel. No considerar certificada la precisión E0/E1/E2 ni las dimensiones físicas.

## Al acabar

Detener en orden túnel Cloudflare, pasarela y backend con Ctrl+C. La web estática seguirá visible pero no tendrá API. No subir `.agroscan_demo/` a GitHub; se agrega a `.gitignore`.

## Fuentes oficiales

- Vercel Vite: https://vercel.com/docs/frameworks/frontend/vite
- Vercel SPA rewrites: https://vercel.com/docs/routing/rewrites
- Vercel variables: https://vercel.com/docs/environment-variables
- Cloudflare Quick Tunnel: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
