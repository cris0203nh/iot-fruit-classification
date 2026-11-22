# Suscripciones DEMO — revisión local

Base: `origin/main` actualizado (`5f87640`, PR #91). Rama: `feature/saas-demo-subscriptions`. Sin commit, publicación ni migración operativa.

## Auditoría y decisiones

- Se revisaron `App`, `AuthGate`, `PlatformDashboard`, `AdminDashboard`, navegación, estilos, cliente HTTP, modelos, autorización, Alembic, SaaS-03–08 y workflows 02–07. Se reutilizan JWT/Google, selección empresarial, permisos vigentes y registro por invitación. `OrganizationMembership` sigue representando roles; no es una suscripción comercial.
- Las pantallas existentes tienen un lenguaje editorial verde/papel, controles accesibles y navegación móvil con foco confinado. Los paneles empresarial/global carecían de contexto comercial; había operaciones administrativas sensibles sin confirmación. Se añaden resumen comercial, catálogo, checkout, estados explícitos y confirmaciones; los controles operativos se conservan. El refinamiento de jerarquía, espaciado y formularios es compartido, sin sustituir captura, revisión o historial.
- No hay autorregistro público de empresas ni privilegios: el propietario usa el alta existente; los nuevos usuarios usan la invitación segura existente. Google conserva su vinculación explícita.
- Ningún plan bloquea operaciones existentes. Los límites son informativos y se presentan como tales. No hay pasarela, cobro real, facturación ni renovación automática.

## Persistencia y autorización

Migración **`c009commerce`**, posterior a `s007iot`: cuatro tablas nuevas, sin inserciones ni modificaciones de tablas operativas:

| Tabla | Función |
|---|---|
| `commercial_plans` | Versiones inmutables de condiciones, precio entero en céntimos PEN, periodo, beneficios y límites; activación administrable |
| `commercial_subscriptions` | Una suscripción por empresa, copia de condiciones, vigencia UTC; estado visible activo/cancelado/vencido |
| `commercial_orders` | UUID, importe calculado en servidor, copia histórica, acción, estado y clave idempotente única por empresa |
| `commercial_transactions` | Resultado DEMO, actor y fecha; FK compuesta a orden de la misma empresa y una transacción por orden |

Las tres tablas empresariales reutilizan el filtro ORM y las restricciones SaaS. Solo el administrador activo de la organización activa puede contratar, renovar, cancelar y consultar su historial; el propietario tiene consulta global separada. Operadores/revisores conservan su operación y acceso al catálogo público.

`BEGIN IMMEDIATE` serializa la comprobación y escritura; orden, transacción y suscripción se confirman atómicamente. Repetir una clave con condiciones distintas o cambiar un resultado definitivo devuelve 409. Reintentar la misma confirmación no vuelve a extender la vigencia. Una orden pendiente vence a las 24 horas. Las renovaciones usan meses/años de calendario; un cambio comienza una nueva vigencia sin prorrateo. El vencimiento se calcula al consultar; no requiere tarea programada.

Estados de orden: `pending`, `demo_approved`, `demo_rejected`, `cancelled`. Solo una aprobación activa/renueva la suscripción. La cancelación es inmediata y conserva el historial; no modifica permisos operativos. Las condiciones de versiones anteriores no se reescriben. La reversión elimina **solo las cuatro tablas comerciales y sus datos DEMO**; requiere decisión explícita y exportación previa si se desea conservarlos.

| Endpoints | Autorización |
|---|---|
| `GET /api/commercial/plans` | Público; solo catálogo y disponibilidad del simulador |
| `GET /api/commercial/subscription` | Administrador de empresa; plan, órdenes y transacciones propias |
| `POST /api/commercial/orders` | Administrador + entorno DEMO habilitado; `planId`, `action`, `idempotencyKey` |
| `POST /api/commercial/orders/{id}/confirm` | Mismo contexto; `scenario`: `approve`, `reject`, `cancel` |
| `POST /api/commercial/subscription/cancel` | Mismo contexto; cancelación repetible sin duplicados |
| `GET, POST /api/platform/commercial/plans` | Propietario; consulta y publicación de versiones |
| `PATCH /api/platform/commercial/plans/{id}/status` | Propietario; solo la última versión puede reactivarse |
| `GET /api/platform/commercial/overview` | Propietario; métricas, suscripciones y operaciones exclusivamente DEMO |

## Ejecutar sin tocar la base original (PowerShell)

Usar una consola nueva desde la raíz y puertos locales libres. No detener ni reutilizar una API operativa para este ensayo.

```powershell
$demoRoot = Join-Path $env:TEMP ('agroscan-commerce-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $demoRoot | Out-Null
$env:AGROSCAN_DATA_DIR = $demoRoot
$env:AGROSCAN_DATABASE_URL = 'sqlite:///' + ($demoRoot.Replace('\', '/')) + '/agroscan.db'
$env:AGROSCAN_JWT_SECRET = & .\backend\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
$env:AGROSCAN_ENVIRONMENT = 'demo'
$env:AGROSCAN_SUBSCRIPTION_SIMULATOR = 'true'
Set-Location backend
& .\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migración de ensayo fallida' }
& .\.venv\Scripts\python.exe -m app.bootstrap_owner --create-user
if ($LASTEXITCODE -ne 0) { throw 'Inicialización de propietario fallida' }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

El bootstrap solicita usuario y contraseña privados; no existen credenciales predeterminadas. En otra consola desde la raíz:

```powershell
npm ci --prefix frontend
npm run dev --prefix frontend -- --host 127.0.0.1
```

Abrir `http://127.0.0.1:5173`. Como propietario: publicar un plan DEMO con precio ilustrativo elegido explícitamente; registrar empresa de ensayo y administrador mediante el panel existente. Cerrar sesión. Abrir `/planes`, seleccionar plan, iniciar sesión como ese administrador, revisar resumen, preparar orden y confirmar escenario. Debe aparecer **«Pago simulado — No se realizó ningún cobro»**. `/suscripcion` recupera el historial tras recargar e iniciar sesión y permite continuar órdenes pendientes, cambiar, renovar o cancelar. Probar rechazo/cancelación antes de aprobación; ninguno debe activar una suscripción. El propietario consulta métricas reales de estas operaciones simuladas.

Fuera de esta consola, no configurar las dos variables del simulador. Por defecto las escrituras comerciales devuelven 503; el catálogo e historial siguen consultables. Desactivar el simulador no borra evidencia DEMO. No apuntar estos comandos a la base original.

## Verificación y límites

Resultados locales (Windows, Python 3.13.15, Node 24.19.0): backend **457 aprobadas + 3 omisiones preexistentes**, frontend **153 aprobadas + 1 omisión preexistente**, visión **569 aprobadas + 2 omisiones preexistentes**, I03 **12**, IoT Python **25**, proxy **7**, ScaleCore C++ **16 grupos**, contratos CI **51**, normalizador de seguridad **19**; cero fallos. Lint/build aprobados. Bandit de código comercial y SCA actual de backend/IoT/npm completo/npm producción: cero hallazgos. Las nuevas pruebas son 15 backend y 10 frontend. Upgrade/repetición/downgrade/nuevo upgrade conservan los hashes de todas las filas operativas sintéticas e integridad/FK; también se ejecutó la cadena completa en una base vacía aislada.

Se ejecutó adicionalmente el cliente TypeScript real contra FastAPI mediante HTTP local: catálogo, login, contexto empresarial, contratación, reintento, renovación, rechazo, cancelación y métricas globales. Base de ensayo separada: cuatro órdenes y cinco eventos DEMO, sin duplicar la confirmación repetida. Evidencias y lista de archivos locales en `.agroscan-checkpoints/commercial/resultados.json` (ignorado por Git); el servidor de ensayo se cerró al terminar.

Pruebas nuevas: precios manipulados, autorizaciones, A/B, relaciones indirectas, persistencia, escenarios, cambios de versión, idempotencia concurrente, fallo transaccional, calendario, vencimiento, revocación, configuración deshabilitada y migración repetida/reversible en copia sintética. Frontend: contratos HTTP, estados devueltos por servidor, recarga, navegación, aviso DEMO, formularios/tabla accesibles y responsive, más renderizado React real de estados iniciales. Los workflows permanecen intactos; las pruebas nuevas entran en descubrimiento backend y `npm test`.

Pendientes: revisión visual interactiva en navegador (no disponible en esta sesión), validación teclado/lectores de pantalla y dispositivos reales, ejecución remota completa en GitHub Actions, Google OAuth y hardware reales. El build avisa del tamaño del bundle; no se desactiva el aviso. Las pruebas físicas y symlinks no disponibles conservan sus omisiones preexistentes; no se añadieron `skip`. Este módulo no acredita exactitud de IA ni preparación comercial, legal o financiera.
