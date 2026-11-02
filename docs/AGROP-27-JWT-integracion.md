# AGROP-27 — Integración de autenticación AGROP-47 (PATCH 03)

## Alcance

- Pantalla de acceso de operador con `POST /api/auth/login` y verificación de roles por `GET /api/auth/me`.
- Token JWT almacenado solo en memoria de la pestaña: no localStorage, no cookies, no query strings, no registros en consola.
- Encabezado Bearer en las solicitudes de evaluación, subida de evidencias y consultas de historial.
- Carga de imágenes protegidas mediante `fetch` autenticado + `Blob` temporal; revoca las URL de objeto al desmontar.
- Conserva el registro de múltiples vistas de PATCH 02; no modifica FastAPI ni cambia roles o permisos.

## Límites y precauciones

- Sesión no persistente: al recargar la página hay que volver a iniciar sesión.
- Tras expirar JWT (configurado en backend), cerrar sesión e ingresar nuevamente.
- Solo cuentas existentes con rol `operador` o `administrador` pueden entrar a la interfaz de captura.
- El usuario deberá hacer una validación manual mínima con dos imágenes de la misma pieza y un solo ID para cerrar Jira. Las pruebas aisladas no sustituyen integración.
- No subir archivos `.env`, secretos JWT, contraseñas, tokens ni imágenes de Swagger que contengan credenciales.

## Verificación

1. `git apply --check PATCH_AGROP27_03_JWT_INTEGRACION.patch`
2. `git apply PATCH_AGROP27_03_JWT_INTEGRACION.patch`
3. `cd frontend && npm test && npm run lint && npm run build`
4. FastAPI activo; frontend desde `npm run dev`. Inicio de sesión con usuario local operador válido.
5. Crear una evaluación y guardar `vista-1`, confirmar giro y `vista-2`; revisar `Historial > Detalle` y recargar tras iniciar sesión otra vez.

No fusionar el PR si las pruebas integradas muestran errores 401, 403, 409 o fallo de imágenes.
