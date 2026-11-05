# Incremento 04 — Remediación DAST y validación de seguridad HTTP

## Línea base

- Rama de trabajo: `security/devsecops-hardening`. No fusionar en `main`.
- Reporte DAST del Incremento 03 (`devsecops-zap-dast/zap.json`): 5 reglas, 33 ocurrencias: `10021` LOW (2), `90004` LOW (2), `10049` INFO (5), `10111` INFO (2), `100000` INFO (22). **Son alertas por regla, no vulnerabilidades únicas confirmadas.**
- El reporte está sanitizado; no contiene URLs ni las subreglas exactas de `90004`. No se puede afirmar que esta última desaparezca sin volver a ejecutar ZAP.

## Modificaciones

1. Middleware ASGI puro en `backend/app/http_security.py`, instalado después de CORS en `backend/app/main.py`, para incluir respuestas de preflight y errores HTTP esperados.
2. `X-Content-Type-Options: nosniff` en respuestas HTTP, incluidas respuestas JSON, errores HTTP y documentación.
3. `Cross-Origin-Resource-Policy: same-origin` en recursos servidos por el backend; bloquea cargas *no-cors* desde otro origen. Las peticiones `fetch` con CORS explícito de React y la recuperación de evidencias mediante `blob:` siguen siendo el contrato de integración previsto.
4. `Referrer-Policy: no-referrer` para evitar referencias que pudieran exponer rutas.
5. `Cache-Control: no-store` para todas las rutas bajo `/api/` (también 401/403/404 y respuestas de preflight): ninguna respuesta dinámica de la API debe persistirse en cachés de navegadores/proxies. No se aplica a `/docs` ni `/openapi.json`.
6. `Cross-Origin-Opener-Policy: same-origin` en documentos `/docs` y `/redoc`. **No** se activa `Cross-Origin-Embedder-Policy: require-corp` de forma global: la documentación interactiva usa recursos de terceros y podría dejar de funcionar. Esta decisión es deliberada y debe revisarse antes de un despliegue público.
7. Pruebas de regresión de cabeceras, CORS para los dos orígenes locales autorizados, origen ajeno, 401/403, rutas inexistentes y documentación. El smoke del DAST verifica las cabeceras y preflight en la instancia temporal real antes del escaneo.

## Validaciones locales

En PowerShell, desde el worktree independiente:

```powershell
$env:AGROSCAN_JWT_SECRET = & .\backend\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
$env:PYTHONPATH = "backend"
& .\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_*.py" -v
& .\backend\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -p "test_*.py" -v
& .\backend\.venv\Scripts\python.exe -m unittest discover -s scripts/devsecops -p "test_*.py" -v
npm run lint --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
git diff --check
```

Después del `push`, revisar que todos los jobs estén aprobados y descargar nuevamente **solo `devsecops-zap-dast`** para comparar reglas y ocurrencias antes/después. El gate continúa bloqueando alertas `HIGH` y `CRITICAL`; el estado verde **no** implica ausencia de alertas `LOW` o `MEDIUM`.

## Criterios de aceptación y riesgo residual

- `10021`: debería desaparecer tras instalar `nosniff`; confirmar con ZAP real.
- `90004`: puede persistir según la subregla que haya detectado ZAP; falta dato de subregla en el informe normalizado. No se recomienda añadir COEP sin evaluar Swagger, el frontend y los recursos externos en un navegador real.
- `10049`: es informativo; respuestas `no-store` pueden seguir generando esta regla. No eliminar `no-store` solo para conseguir cero avisos.
- `10111` y `100000`: informativos; contrastar rutas y códigos con pruebas negativas.
- El análisis DAST sigue siendo **pasivo y principalmente no autenticado**. Falta una validación autenticada por roles y una prueba en navegador antes de certificar el comportamiento completo.
- El middleware de aplicación cubre respuestas normales y excepciones HTTP manejadas. Los errores generados fuera de la pila ASGI de la aplicación (p. ej., proxies o ciertos 500 no controlados) requieren configuración del gateway y verificación en despliegue.

## Referencias técnicas

- https://www.zaproxy.org/docs/alerts/10021/
- https://www.zaproxy.org/docs/alerts/90004/
- https://www.zaproxy.org/docs/alerts/10049/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Resource-Policy
- https://www.starlette.io/middleware/
