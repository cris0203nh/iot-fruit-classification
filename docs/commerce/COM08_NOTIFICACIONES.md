# COM-08 — Notificaciones transaccionales

## Integración y límites

`c018notifications` (desde `c017catalog`) añade únicamente `commercial_notification_outbox`; no cambia contratos ni genera correos retroactivos. Intención y operación comercial comparten transacción. El transporte SMTP ocurre después del commit, sin mantener una transacción SQLite durante la conexión.

Eventos: solicitud recibida (propietario), aprobada/rechazada (contacto), invitación inicial preparada y acceso incorporado, suscripción DEMO activada/renovada/cambiada/cancelada y recordatorios de próximo vencimiento/vencimiento. Solo una confirmación DEMO aprobada genera los eventos de contratación. Borradores y publicación de catálogo no notifican ni modifican suscripciones.

Destinatarios: contacto persistido de la solicitud; administradores activos de la empresa con correo de invitación aceptada o identidad Google vinculada; propietario mediante `AGROSCAN_COMMERCIAL_OWNER_EMAIL`. Usuarios históricos sin correo verificable producen `omitted`, sin inventar direcciones. Se revalidan membresías y disponibilidad de invitaciones antes del envío. Los enlaces secretos de invitación continúan entregándose manualmente por COM-04; ningún token se guarda en el outbox.

`pending` → `processing` → `smtp_accepted`, `retry_pending` o `failed`; `omitted` identifica falta de destinatario/autorización. Aceptación SMTP **no prueba entrega en buzón**. Sin SMTP, la intención queda pendiente con error sanitizado y fecha del siguiente intento, sin consumir intentos de transporte. Una dirección ausente al crear el evento queda omitida: configurar el correo antes de nuevos eventos.

Claves únicas por evento/referencia/destinatario; reclamación condicional y durable antes de SMTP. Backoff exponencial acotado; máximo configurable. Un timeout, desconexión, resultado incierto o fallo al guardar después de SMTP no se reenvía automáticamente. Reclamaciones abandonadas por más de diez minutos pasan a `failed/delivery_uncertain` al procesar la cola. Resolver manualmente con evidencia del proveedor; no existe garantía SMTP exactly-once ni botón para forzar duplicados.

COM-05R1 conserva su respuesta y tabla c013 como proyección compatible. Nuevas solicitudes usan el outbox; los registros anteriores no se reencolan ni se envían otra vez. El POST público mantiene su intento inmediato acotado; los demás eventos los procesa el comando explícito o el reintento del propietario.

Archivos incorporados: `backend/app/notification_models.py`, `backend/app/notification_worker.py`, `backend/app/services/commercial_notifications.py`, `backend/app/routers/notifications.py`, `backend/alembic/versions/c018notifications_com08.py`, `backend/tests/test_com08_notifications.py`, `frontend/src/features/commercial/Notifications.tsx`, `frontend/src/features/commercial/notificationsApi.ts`, `frontend/tests/com08-notifications.test.mjs` y este documento.

Archivos adaptados: `backend/alembic/env.py`, `backend/app/main.py`, `backend/app/routers/applications.py`, `backend/app/routers/commercial.py`, `backend/app/services/application_notification.py`, `backend/app/services/invitations.py`, `backend/tests/test_com02_applications.py`, `backend/tests/test_com05r1_notifications.py`, `frontend/package.json`, `frontend/src/app/navigation.ts`, `frontend/src/pages/OwnerWorkspace.tsx` y `tools/agroscan_qa.py`. Las pruebas de datos protegidos excluyen únicamente la nueva tabla auxiliar; pruebas COM-08 verifican sus efectos. El guard de QA/DEV exige la nueva revisión, sin migración automática.

## API y panel

- `/plataforma/notificaciones`: sección del propietario con filtros, estadísticas reales, SMTP disponible/ausente, fechas e intentos.
- `GET /api/platform/notifications`: filtros `organization_id`, `event`, `status`, `since`, `until`, `limit` y `offset`; fechas UTC. Respuestas privadas `no-store`.
- `POST /api/platform/notifications/{id}/retry`: cuerpo `{}`, solo pendientes elegibles, espera y máximo comprobados en servidor. Nunca acepta destinatarios/cuerpos personalizados. Reutiliza autenticación y CSRF existentes. Otros roles: 403.

## Configuración (solo backend, sin secretos en Git)

| Variable | Uso / valor predeterminado |
|---|---|
| `AGROSCAN_SMTP_ENABLED` | Solo `true` habilita SMTP; ausente deshabilitado |
| `AGROSCAN_SMTP_HOST`, `AGROSCAN_SMTP_PORT` | Servidor y puerto |
| `AGROSCAN_SMTP_SECURITY` | `starttls` (587) o `ssl` (465); `plain` solo loopback de pruebas |
| `AGROSCAN_SMTP_USERNAME`, `AGROSCAN_SMTP_PASSWORD` | Credenciales del transporte; nunca OAuth/JWT de usuarios |
| `AGROSCAN_SMTP_FROM`, `AGROSCAN_SMTP_FROM_NAME` | Remitente autorizado; nombre comercial por defecto AgroScan |
| `AGROSCAN_SMTP_TIMEOUT_SECONDS` | 5 segundos; rango 1–30 |
| `AGROSCAN_COMMERCIAL_OWNER_EMAIL` | Correo autorizado del propietario |
| `AGROSCAN_PUBLIC_URL` | Origen HTTPS público para enlaces; HTTP solo localhost/127.0.0.1; sin ruta/query |
| `AGROSCAN_NOTIFICATION_MAX_ATTEMPTS` | 5; rango 1–10 |
| `AGROSCAN_NOTIFICATION_RETRY_SECONDS` | Espera base 60; rango 1–86400, exponencial hasta 86400 |
| `AGROSCAN_NOTIFICATION_EXPIRY_DAYS` | Ventana previa 7 días; rango 1–90 |
| `AGROSCAN_NOTIFICATION_EXPIRED_LOOKBACK_DAYS` | Ventana posterior 30 días; rango 1–365 |

Gmail: usar `smtp.gmail.com` con STARTTLS/587 o SSL/465 ([puertos oficiales](https://developers.google.com/workspace/gmail/imap/imap-smtp)). Si la cuenta permite contraseñas de aplicación, activar verificación en dos pasos y generar una exclusiva para AgroScan; puede no estar disponible según las políticas de cuenta ([ayuda de Google](https://support.google.com/accounts/answer/185833?hl=es)). No usar la contraseña habitual. Este módulo reutiliza SMTP usuario/contraseña, no implementa XOAUTH2 ni cambia Google Sign-In.

En la terminal privada del backend/worker, con cuenta y destinatario de ensayo autorizados:

```powershell
$env:AGROSCAN_SMTP_ENABLED = 'true'
$env:AGROSCAN_SMTP_HOST = 'smtp.gmail.com'
$env:AGROSCAN_SMTP_PORT = '587'
$env:AGROSCAN_SMTP_SECURITY = 'starttls'
$env:AGROSCAN_SMTP_FROM_NAME = 'AgroScan'
$env:AGROSCAN_SMTP_USERNAME = Read-Host 'Cuenta remitente autorizada'
$env:AGROSCAN_SMTP_FROM = $env:AGROSCAN_SMTP_USERNAME
$env:AGROSCAN_COMMERCIAL_OWNER_EMAIL = Read-Host 'Destinatario propietario de ensayo autorizado'
$secret = Read-Host 'Contraseña de aplicación (entrada oculta)' -AsSecureString
try { $env:AGROSCAN_SMTP_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password }
finally { $secret.Dispose(); Remove-Variable secret }
# Al terminar los procesos de prueba:
# Remove-Item Env:AGROSCAN_SMTP_PASSWORD
```

## Ejecución explícita

Antes de usar el código nuevo: detener servicios de la instancia elegida, respaldar con `sqlite3.Connection.backup()`, verificar integridad/FK y ensayar la migración en una copia. **Esta implementación no migró DEV, QA ni la base histórica.** La guarda de arranque exige c018; no omitirla. Conservar configuración JWT/instancia existente.

Desde la raíz, en una terminal dedicada y solo para el directorio autorizado:

```powershell
$python = "$env:USERPROFILE\Documents\AgroScan-Python-Probe\Scripts\python.exe"
$env:AGROSCAN_DATA_DIR = Read-Host 'Directorio absoluto de datos autorizado'
$database = Join-Path $env:AGROSCAN_DATA_DIR 'agroscan.db'
if (-not (Test-Path -LiteralPath $database -PathType Leaf)) { throw 'Base inexistente' }
$env:AGROSCAN_DATABASE_URL = 'sqlite:///' + $database.Replace('\','/')
$env:PYTHONPATH = Join-Path $PWD 'backend'
# Solo tras respaldo/ensayo aprobados, con la conexión comprobada:
Push-Location backend
& $python -B -m alembic current
& $python -B -m alembic upgrade c018notifications
if ($LASTEXITCODE -ne 0) { throw 'Migración fallida; detenerse sin restaurar automáticamente' }
Pop-Location
# Ejecutar recordatorios y después transporte; no altera vigencias ni estados contractuales.
& $python -B -m app.notification_worker reminders --limit 100
& $python -B -m app.notification_worker process --limit 50
```

El worker exige directorio/base existentes, URL coincidente y revisión c018; no crea ni migra. Para programarlo, ejecutar ambos comandos cada cinco minutos con el programador local y entorno privado de la instancia. El límite de recordatorios cuenta nuevas intenciones: los ya registrados no bloquean las siguientes empresas.

Prueba real controlada: usar una base de ensayo ya migrada y exclusivamente contactos autorizados, configurar remitente/destinatario antes del evento, cargar la contraseña de aplicación mediante entrada oculta o gestor local (nunca escribirla en comandos, documentación o frontend), generar una solicitud nueva y procesar. Revisar panel/SMTP y, por separado, buzón/spam del destinatario. No ejecutar un lote sobre contactos reales sin autorización. Borrar la variable de contraseña/cerrar la terminal al terminar. Sin configuración válida y destinatario autorizado, la entrega Gmail permanece **pendiente**, no aprobada.

Automatización: `python -B -m unittest discover -s backend/tests -p 'test_*.py'` con `AGROSCAN_DATA_DIR`, JWT y TEMP externos de ensayo; `npm test`, `npm run lint`, `npm run build` en frontend. Las pruebas SMTP usan transportes simulados. Navegador real, accesibilidad visual y entrega externa deben registrarse por separado.

## Verificación ejecutada — 23/11/2026

| Comprobación | Resultado |
|---|---|
| Backend completo: `python -B -m unittest discover -s backend/tests -p 'test_*.py'` | 573 casos: 570 aprobados, 3 omitidos preexistentes, 0 fallos/errores (204,854 s) |
| Guardas: `python -B -m unittest tests.test_agroscan_qa tests.test_agroscan_dev` | 9/9 aprobados |
| `npm test` (incluye cinco casos COM-08 nuevos) | 232 casos: 231 aprobados, 1 omitido preexistente, 0 fallos |
| `npm run lint` / `npm run build` | Ambos código 0; aviso de bundle >500 kB, sin desactivar controles |
| Gitleaks sobre los 22 archivos cambiados | 0 hallazgos; configuración existente, sin nuevas excepciones |
| Migración temporal c017→c018, repetición y reversión vacía | Conserva filas previas, usuarios y snapshots de planes/suscripciones; integridad/FK correctas; sin correos retroactivos |
| SMTP real, buzón Gmail, navegador real/responsive visual | Pendientes; no ejecutados ni declarados aprobados |

Los 16 casos backend COM-08 cubren eventos confirmados/rechazados, idempotencia, rollback, membresías revocadas, roles/A-B, destinatarios manipulados, SMTP habilitado/ausente, autenticación/conexión/timeout, concurrencia, backoff/máximo, aceptación seguida de fallo de escritura, HTML seguro, tokens ausentes, migración y recordatorios por lotes sin alterar contratos. COM-02–07 y autenticación pasan dentro de la suite completa. Omisiones existentes: dos pruebas experimentales requieren evidencia real autorizada, una requiere symlinks permitidos en Windows y la frontend requiere evidencia de inferencia real.

Evidencias locales fuera del repositorio: `com08-backend-final.log`, `com08-tools-final.log`, `com08-frontend-final.log` y `com08-source-gitleaks.json`, en el directorio privado de respaldos utilizado durante la intervención. No se modificaron SQLite operativas, credenciales, IA, firmware ni workflows. Sin commit, push, merge ni despliegue.
