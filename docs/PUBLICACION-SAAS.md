# Publicación SaaS-01–08

Rama local: `feature/agroscan-saas-multiempresa`, basada en `origin/main` actualizado. No se creó commit, PR remoto ni despliegue. El índice contiene código, migraciones, pruebas y guías SaaS; los artefactos privados se retiraron solo del índice, conservando sus archivos físicos.

| Contenido | Tratamiento |
|---|---|
| Backend/React SaaS, cuatro migraciones `s003organizations`–`s007iot`, pruebas, bridge autenticado existente | Incluido; sin cambios nuevos de IA/firmware. SaaS-01/02/05/08 no añaden revisión Alembic propia. |
| 51 fotos operativas y 51 copias de las mismas fotos en informes | Excluidas; coincidencias SHA-256 comprobadas. |
| Cuatro SQLite temporales AG046 | Excluidos: usuarios sintéticos, artefactos regenerables, no fixtures requeridos. |
| Informes, particiones y CSV con referencias operativas | Excluidos; incluso el CSV denominado `revisiones_dataset.template.csv` contenía 28 registros, no solo una plantilla. |
| Fixtures sintéticos en código, ejemplos sin registros privados, icono React y modelos ya versionados | Conservados. Las pruebas generan sus propias bases e imágenes. |
| Datos actuales, respaldos, checkpoints, `.env*`, claves, logs y resultados locales | Ignorados/no incluidos. Otros cambios locales de investigación IA quedan fuera del commit SaaS. |

**Bloqueo histórico:** `origin/main` ya contiene fotos/datos y metadatos operativos. Retirarlos del índice no los retira del historial ni de los diffs de borrado. No publicar la rama/PR hasta acordar el saneamiento histórico con el propietario. No se reescribió historia ni se ejecutó force-push. El examen de 962 blobs de refs remotas (909 de texto, ≤4 MiB) no encontró claves privadas, tokens de proveedores, JWT literales ni coincidencias con secretos actuales; quedó fuera un blob grande y no se acredita historia externa a esas refs.

Validación del árbol limpio preparado: 243 pruebas Python (241 aprobadas, dos omisiones de entorno), 161 frontend (160 aprobadas, una omisión de evidencia de inferencia), build/lint correctos. La copia actual de SQLite ya está en `s007iot`: upgrade idempotente, 25 tablas y hashes de 86 fotografías conservados, integridad/FK correctas. No se migró la original. Continúan sin administrador empresarial activo ni dispositivo aprovisionado; el informe SaaS-08 conserva las mediciones históricas de su cierre.

## Revisión y commit/PR manuales

El cuerpo del PR está preparado localmente en `.agroscan-checkpoints/publication/pr-body.md`. Estos comandos no se ejecutaron; resolver primero el bloqueo histórico y revisar el índice. GitHub CLI necesita autenticación local (`gh auth login`), sin copiar tokens al repositorio:

```powershell
git status --short
git diff --cached --stat
git diff --cached --check
git commit -m "feat: aislar AgroScan SaaS por organización y asegurar autenticación e IoT"
git push -u origin feature/agroscan-saas-multiempresa
gh pr create --draft --base main --head feature/agroscan-saas-multiempresa --title "AgroScan SaaS-01–08: aislamiento, roles, identidades e IoT" --body-file .agroscan-checkpoints/publication/pr-body.md
```

No hacer merge mientras no pasen los controles de datos/historial y despliegue. Conservar las exclusiones y no usar `git add .`.

Antes de actualizar otra copia que aún rastree esos datos, verificar respaldo y almacenamiento persistente fuera del checkout: un pull de las bajas puede retirar los archivos de esa otra copia. No usar `git clean` ni sustituir la carpeta de datos operativa con el árbol limpio de código.

## Vercel y FastAPI

`frontend/.vercel/project.json` coincide con el proyecto remoto **agroscan-demo**, preset Vite; el proyecto no está enlazado a Git. Su raíz remota actual es la raíz de la carga CLI: para integrar Git seleccionar **Root Directory = frontend**, build `npm run build`, salida `dist`. La vinculación local `.vercel/` se conserva privada.

FastAPI/SQLite/fotos/modelos permanecen en el servidor existente con disco persistente, respaldo y HTTPS; desplegar React en Vercel no despliega ni migra ese backend. Falta definir/verificar el origen HTTPS estable. No usar el gateway de demo para SaaS completo: su lista de rutas bloquea plataforma, invitaciones, exportación y operaciones IoT.

Google usa nonce en cookie HttpOnly `SameSite=Strict`: preferir **mismo origen**. Mantener `VITE_API_BASE_URL` vacío en Vercel y añadir, antes del fallback SPA, el proxy `/api` al backend autorizado. La configuración actual solo tiene fallback React; sin proxy `/api` devolvería HTML. Ejemplo para sustituir el destino real **antes** de aplicar/desplegar:

```json
{"headers":[{"source":"/api/:path*","headers":[{"key":"Cache-Control","value":"private, no-store, max-age=0"}]}],"rewrites":[
  {"source":"/api/:path*","destination":"https://backend.example.invalid/api/:path*"},
  {"source":"/(.*)","destination":"/index.html"}
]}
```

Referencia: [rewrites externos de Vercel](https://vercel.com/docs/routing/rewrites). No cachear respuestas empresariales/autenticadas; validar `Set-Cookie`, host, esquema HTTPS y cabeceras reenviadas de extremo a extremo. El origen del frontend debe estar autorizado donde corresponda (`AGROSCAN_DEMO_ORIGINS` y Google OAuth). `AGROSCAN_GOOGLE_CLIENT_ID` y `AGROSCAN_JWT_SECRET` se configuran en backend; ningún secreto en variables `VITE_*`. Google necesita el origen exacto desplegado y vinculación explícita.

Tras saneamiento, backend configurado y pruebas HTTPS A/B (login, cambio de empresa, Google, fotos, revisiones, exportación e IoT), desplegar manualmente desde la raíz:

```powershell
vercel --cwd frontend
# Revisar preview, permisos y persistencia del backend antes de producción:
vercel --cwd frontend --prod
```

No se ejecutó ninguno. La migración real y la activación de dispositivos siguen el mantenimiento de [SaaS-08](SAAS-08.md). Hardware, exactitud E0/E1/E2 y flujo OAuth real no se acreditan mediante build/unit tests.
