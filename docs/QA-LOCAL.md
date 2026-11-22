# AgroScan QA local — cuatro roles y contratación DEMO

**AUTH-01:** el arranque ahora exige `a016sessions` (tabla de sesiones revocables). No se ha migrado la QA existente ni la base histórica. Requiere respaldo y migración explícita antes del próximo arranque. Solo HTTP en loopback permite cookies sin Secure; producción requiere HTTPS y frontend/API del mismo sitio (preferir proxy `/api`). Los orígenes HTTPS adicionales se autorizan con `AGROSCAN_DEMO_ORIGINS`; no se aceptan comodines. Cookie HttpOnly/SameSite Strict, inactividad máxima de siete días y límite absoluto de treinta; renovación cada cinco minutos mientras la aplicación permanece abierta. JWT/CSRF solo en memoria; logout revoca la sesión y sus JWT. No usar caché pública para `/api/auth/*`.

El lanzador QA habilita `AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP=true` solo tras validar sus rutas e identidad. Dejar esta variable sin configurar en producción. Las pruebas de AUTH-01 usan SQLite temporal; SMTP/OAuth reales y F5 visual siguen pendientes de activación QA.

**COM-07:** cierre automatizado y límites en [COM07_CIERRE_INTEGRAL.md](commerce/COM07_CIERRE_INTEGRAL.md). Se corrigió deriva de `images.idempotency_key` mediante `c015imagekey`, probada solo en bases temporales/copias. QA principal permanece c014: el nuevo arranque exige c015 y no la aplica automáticamente. Antes de reiniciar, revisar/aplicar esa migración sobre QA con respaldo autorizado. `-Action verify` puede leer c014 y migrar únicamente su copia desechable; ya no exige historial vacío ni modifica registros de QA. Navegador desktop/móvil y externos continúan pendientes.

**COM-06:** QA usa `c014onboarding` (respaldo verificado; sin backfill). La empresa de ensayo ID 3 quedó `completed`, con suscripción DEMO activa tras probar rechazo/cancelación inicial, aprobación, renovación repetida, cambio, cancelación inmediata y renovación posterior. Se preservaron los registros comerciales que ya existían en otras empresas. Cliente incorporado: credencial DPAPI de `com04-client.clixml`; entrar en `/suscripcion`, consultar referencias/plan e historial. Propietario: `/plataforma/planes?vista=suscripciones` y `?vista=operaciones`, además de la bandeja de solicitudes. Todas las cifras son simuladas; no se enviaron correos ni se ejecutaron cobros. Para probar otra primera contratación, usar otra empresa sintética mediante el flujo público/aprobación/invitación, conservando los registros actuales.

**COM-05R1:** QA usa `c013ownernotice`, aplicada con respaldo verificado, sin modificar filas previas. En `/` y `/planes` el CTA principal es **Solicitar plan**, siempre público; el checkout DEMO es una opción adicional solo para administradores autenticados. Nueva solicitud de ensayo → confirmación pendiente y aviso **correo deshabilitado** → bandeja del propietario. No se han enviado correos reales. Configuración opcional SMTP y límites de idempotencia documentados en `docs/commerce/COM01_CONTRATO_COMERCIAL.md`.

```powershell
# SMTP apagado explícitamente al iniciar/reiniciar QA:
$env:AGROSCAN_SMTP_ENABLED = 'false'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action start
```

**Rutas COM-05:** `/` es la landing pública; `/acceso` abre el login y `/app` conserva el inicio operativo por rol. `/planes`, `/solicitar?plan=ID`, `/suscripcion` y las rutas internas siguen disponibles. Los enlaces antiguos `/#invitation=...` se reciben en la raíz y pasan a la aceptación existente, retirando el fragmento sin trasladar el token a parámetros. Para el flujo público: **Conocer planes → Solicitar plan → Solicitud recibida, pendiente de revisión**. Nada de ello aprovisiona empresas ni registra pagos.

Entorno **ya inicializado** en `.agroscan-qa/data/agroscan.db`, independiente del original. Carpeta ignorada por Git con ACL restringida al usuario de Windows, SYSTEM y administradores. Credenciales y JWT aleatorios se guardan cifrados con DPAPI en `access.clixml`; contraseñas de usuarios con Argon2 en SQLite. No hay contraseñas predeterminadas ni `.env` con secretos.

Migraciones revisadas: cadena existente desde base vacía hasta **`c012initialadmin`** (COM-04, posterior a `c009commerce`/`c010applications`/`c011decisions`), aplicada exclusivamente en QA con respaldo SQLite verificado. Se conservan DEMO A (ID 1), Aislamiento B (ID 2, vacía y sin membresías) y las cuatro cuentas iniciales. El propietario no tiene rol/membresía empresarial; los otros tres usuarios pertenecen solo a A. Tres planes PEN ilustrativos DEMO permiten ensayar mensual/anual; no representan tarifas aprobadas. Las tablas operativas, órdenes, transacciones y suscripciones permanecen vacías. La solicitud sintética aprobada de empresa ID 3 ya tiene un administrador inicial independiente, incorporado por invitación (`awaiting_demo_order`); se conserva también la solicitud rechazada. El arranque exige la revisión esperada y nunca migra otra base automáticamente.

**Recorrido COM-04:** visitante en `/solicitar` → propietario en **Solicitudes comerciales** → aprobar con identidad verificada → **Generar invitación inicial** → confirmar/copiar enlace → abrir en otra sesión/navegador → contraseña propia, cuenta existente explícita o Google configurado → **Ir al panel de AgroScan**. Actualizar la bandeja del propietario para comprobar incorporación. Reemisión revoca el enlace anterior; aceptación no activa una suscripción. La cuenta cliente usada en la demostración tiene credenciales aleatorias cifradas aparte en `.agroscan-qa/com04-client.clixml`, sin modificar las cuatro cuentas originales. Para ensayar el recorrido desde cero, crear otra solicitud sintética con nombre de empresa distinto; no reutilizar el alta ya aceptada ni borrar su trazabilidad. Google real y prueba visual manual siguen pendientes.

```powershell
# Cargar credenciales privadas del cliente QA incorporado (no imprimir contraseña).
$qaClient = Import-Clixml .agroscan-qa/com04-client.clixml
$qaClient.UserName
# Solo para introducirla localmente en el login; nunca guardar/capturar esta salida:
# $qaClient.GetNetworkCredential().Password
```

## Comandos desde la raíz (PowerShell)

```powershell
# Iniciar y abrir manualmente http://127.0.0.1:5188
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action start

# Consultar estado o listar usuarios sin revelar contraseñas
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action credentials

# Revelar UNA contraseña solo en tu consola privada; cambiar Role según necesidad
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action credentials -Role operador -Reveal

# Detener solo los procesos QA registrados; conserva base/cuentas y operaciones
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action stop
```

`-ExecutionPolicy Bypass` es solo para ese proceso: fue necesario para ejecutar los scripts locales sin firma; no se modifica ninguna política persistente. Las credenciales solo pueden descifrarse con el usuario de Windows que las generó. No compartir consola/logs con contraseñas reveladas ni exportar la carpeta QA. Para otro equipo nuevo, `-Action init` genera credenciales nuevas, pero **rechaza sobrescribir un entorno existente**. No repetir `init` sobre este entorno.

## Separación de conexiones

- Backend: **127.0.0.1:8778**; frontend: **127.0.0.1:5188**, marcado «QA LOCAL». No se utilizan los puertos operativos 8000/5173.
- Arranque fija `AGROSCAN_DATA_DIR`, URL SQLite, JWT propio y bandera DEMO solo en procesos hijos, restaurando el entorno del lanzador. El wrapper rechaza rutas discordantes, enlaces, identidad equivocada o migraciones pendientes. No hay migración automática al arrancar.
- `AGROSCAN_ENVIRONMENT=demo` y `AGROSCAN_SUBSCRIPTION_SIMULATOR=true` solo en QA. Google y orígenes externos quedan deshabilitados explícitamente en el wrapper; no se hereda el OAuth real de `backend/.env`.
- `vite.qa.config.ts` reutiliza la configuración normal pero carga un directorio de entorno vacío, rechaza `VITE_API_BASE_URL`, fija el proxy local y verifica la identidad QA antes de reenviar solicitudes. El backend también exige esa identidad; los JWT y membresías siguen siendo obligatorios. Un puerto ocupado o una caída de QA **no** provocan conexión alternativa a la base original.
- No usar `npm run dev` ni `uvicorn app.main:app` directamente para este ensayo: usar el lanzador. No abrir otra URL por error.

## Recorrido visual

| Rol / usuario | Revisar |
|---|---|
| Propietario / `qa_propietario` | Empresas A/B, administradores, catálogo y métricas DEMO; sin autoridad empresarial implícita |
| Administrador / `qa_administrador` | Inicio, usuarios de A, `/suscripcion`; seleccionar desde `/planes`, preparar y confirmar compra DEMO; renovar/cancelar y consultar historial |
| Operador / `qa_operador` | `/evaluacion`, lotes e historial inicialmente vacíos; gestión de usuarios/suscripción denegada |
| Revisor / `qa_revisor` | `/revisiones`, historial y trazabilidad vacíos; alta de lotes/evaluaciones y administración denegadas |

Cerrar sesión entre cuentas; el JWT permanece solo en memoria. La compra manual sí persiste en QA y el reinicio la conserva. Revisar loading/empty/error, foco/Tab/Escape, móvil/tablet y aviso «Pago simulado — No se realizó ningún cobro». No se valida cámara, báscula, IA experimental ni Google real con este recorrido.

## Verificación inicial reproducible

```powershell
# Ejecutar después de start y antes de crear operaciones manuales
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action verify
```

Comprueba los cuatro logins mediante el cliente TypeScript real y proxy QA, permisos, empresa B denegada, catálogo y banner. Después prueba compra/renovación/rechazo/cancelación/idempotencia y acceso A/B sobre **una copia temporal**, descartándola y verificando que la base QA sigue intacta. El administrador B de ese control existe únicamente en la copia. `verify` exige el estado inicial vacío; no elimina ni reinicia operaciones manuales posteriores.

Resultados locales: backend **457 aprobadas + 3 omisiones preexistentes**, frontend **153 aprobadas + 1 omisión preexistente**, guardas QA **4/4**, limpieza sintética **12/12**, contratos CI **51/51**. Lint/build aprobados; aviso existente de bundle >500 kB. Compra en copia: cuatro órdenes/cinco eventos DEMO, sin duplicación. Arranque/parada/reinicio e intento de cambiar el destino al puerto original verificados. Base original y tres archivos de limpieza conservan sus hashes. No se añadieron omisiones ni se tocaron workflows, IA o firmware.

Pendiente: validación visual interactiva por el usuario (ningún navegador disponible para automatización en esta sesión). No se declara preparación comercial. La base original no se limpió ni migró. Estado y evidencias sin secretos: `.agroscan-qa/manifest.json`, `commerce-verification.json`, `resultados.json` y logs de pruebas (ignorados por Git).
