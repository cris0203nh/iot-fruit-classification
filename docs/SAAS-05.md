# SaaS-05 — panel de administración SaaS

- Panel exclusivo del propietario, también cuando no tiene membresías empresariales. El login verifica nuevamente `/api/platform/me` antes de habilitarlo; no lo convierte en administrador empresarial. Cada endpoint `/api/platform/*` exige propietario vigente y usuario activo. El acceso global de la sesión solo permite lecturas agregadas de recursos operativos, sin eludir el aislamiento de sus endpoints.
- Consulta, registro, activación y suspensión de empresas; nombres comprobados en una transacción SQLite para evitar altas simultáneas duplicadas. Métricas reales de empresas, usuarios y evaluaciones. Los usuarios globales se cuentan una sola vez; los totales por empresa deduplican sus membresías y cuentan evaluaciones existentes.
- Designación y retirada de administradores empresariales, con usuarios existentes o nuevas cuentas locales cuyas credenciales introduce el propietario. Solo se modifican membresías de la empresa indicada, sin conceder privilegios globales. El alta privada reutiliza validaciones y Argon2; sus errores no devuelven contraseñas. Una instalación vacía también queda preparada con los tres roles empresariales existentes.
- Gestión empresarial existente conservada y probada con A/B: cada administrador ve y gestiona su empresa. Suspender una empresa o retirar una designación impide inmediatamente las siguientes operaciones autorizadas con JWT anteriores. Reactivar la empresa no reactiva membresías revocadas. IoT y respaldos HTTP siguen bloqueados con 503, incluso para el propietario.
- **94 pruebas backend y 136 frontend aprobadas**, incluyendo resumen React renderizado, autorización, operaciones administrativas, concurrencia, aislamiento, contraseñas y regresiones. Una prueba previa de inferencia omitida por falta de evidencia aislada. Build, lint y `git diff --check` correctos. No se añadieron dependencias, migraciones ni cambios al motor SQLite para SaaS-05.

## Propietario privado: preparado, sin activar

No se promovieron cuentas históricas. `bootstrap_owner.py --check` se ejecutó en modo de solo lectura sobre la configuración original y detectó que faltan las migraciones de SaaS-04; canceló sin modificar la base. No se creó ninguna cuenta ni se introdujeron credenciales reales.

Cuando las migraciones previas se hayan aplicado en mantenimiento autorizado, ejecutar personalmente en PowerShell:

```powershell
Set-Location .\backend
$env:AGROSCAN_DATA_DIR = (Resolve-Path '.\data').Path
.\.venv\Scripts\python.exe -m app.bootstrap_owner --create-user
```

El comando comprueba los requisitos antes de pedir usuario nuevo, nombre y contraseña confirmada. No contiene credenciales predeterminadas ni contraseñas en argumentos. Cancela si la consola no puede ocultar la contraseña, si el usuario existe o si ya hay propietario. La cuenta nueva es exclusiva de plataforma, sin membresías automáticas. Las migraciones y la creación en la base original no se ejecutaron.

Archivos nuevos: `backend/app/routers/platform.py`, `backend/tests/test_saas05_platform.py`, `frontend/src/pages/PlatformDashboard.{tsx,css}`, `frontend/tests/saas05-platform.test.mjs` y este informe. Adaptados: `backend/app/bootstrap_owner.py`, `backend/app/organization_scope.py`, `backend/app/main.py`, `backend/app/routers/auth.py`, `frontend/src/features/auth/AuthGate.tsx`, `frontend/src/services/agroscanApi.ts` y `frontend/package.json`.

Pendientes: aplicar las migraciones previas y crear personalmente el propietario con credenciales propias para usar el panel sobre la instancia original. Google e invitaciones corresponden a SaaS-06 y no se implementaron; sin facturación, suscripciones, cambios de IA/firmware, commit, push ni avance al siguiente incremento.
