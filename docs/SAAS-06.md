# SaaS-06 — Google e invitaciones

- Google: verificación RS256 con claves oficiales, issuer, audience, expiración, sub y nonce ligado a cookie HttpOnly de cinco minutos. El backend emite el JWT local existente; roles, empresa y revocaciones siguen consultándose en la base de datos.
- Vinculación explícita desde una sesión local, confirmando contraseña. Nunca se fusionan cuentas por correo ni se concede superadmin desde Google. El propietario existente conserva su identidad y privilegio existente.
- Invitaciones: administrador de la empresa actual, tres roles empresariales permitidos, token aleatorio almacenado solo como SHA-256, uso único, revocación y caducidad predeterminada de 48 horas (máximo siete días). Se revalidan empresa, administrador emisor y membresías al aceptar. No reemplazan membresías existentes.
- En Usuarios se genera el enlace para entrega manual. El token viaja en el fragmento, se retira antes de cargar Google y se envía al backend en JSON. Se puede aceptar creando una cuenta local, confirmando una cuenta local existente o mediante Google con correo verificado coincidente e invitación explícita.

## Configuración pendiente

1. Crear un cliente OAuth de tipo **Aplicación web** en Google Auth Platform y configurar marca/audiencia según la [guía oficial](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid). Autorizar los orígenes JavaScript `http://localhost` y `http://localhost:5173` para desarrollo, y el origen HTTPS real de producción. Esta integración usa callback JavaScript, sin URI de redirección.
2. Añadir `AGROSCAN_GOOGLE_CLIENT_ID=<ID del cliente web>` al entorno privado del backend y reiniciarlo. El frontend obtiene ese identificador público por API; no requiere client secret ni dependencias npm de Google. Mantener frontend/API en el mismo origen (proxy Vite en desarrollo) para la cookie del desafío; HTTPS en producción.
3. Aplicar `s006identity` mediante el procedimiento Alembic existente durante mantenimiento, después del respaldo correspondiente. No se aplicó a los datos originales. Para vincular al propietario: acceso tradicional → Vincular Google → confirmar contraseña → seleccionar su cuenta Google.

Sin el ID OAuth, Google permanece deshabilitado con acceso tradicional disponible. La prueba real contra Google queda pendiente de configuración. No se requiere servicio de correo ni tarjeta. Se reutiliza PyJWT con su soporte RSA (`cryptography`); instalar las dependencias declaradas del backend si falta ese soporte.

## Verificación y archivos

- Migración `s006identity`: añade únicamente `google_identities`, `google_challenges` y `organization_invitations`. Copia aislada: upgrade repetido y downgrade conservan las 20 tablas históricas, 86 fotografías, propietario y hashes; integridad y claves foráneas correctas, cero vinculaciones automáticas. Downgrade bloqueado si existen identidades o invitaciones.
- Backend: 106 pruebas aprobadas; frontend: 147 aprobadas y una omisión previa de inferencia. Incluyen firmas RSA reales con claves sintéticas, tokens inválidos, repetición, revocaciones, vencimiento, aceptación concurrente, autorización y aislamiento A/B. Build y lint correctos.
- Backend: nuevos modelos, migración, servicios Google/invitaciones, routers y pruebas `test_saas06_*`; ajustes de registro en `models.py`, `organization_scope.py`, `main.py`, requisitos y la matriz de rutas públicas de `test_saas03_organizations.py`.
- Frontend: `GoogleAccess.tsx`, `googleGis.ts`, `InvitationAcceptance.tsx`, `InvitationManager.tsx`; ajustes mínimos en `AuthGate`, `UsersPage`, `agroscanApi.ts`, comando de pruebas y pruebas de seguridad/identidad.

IoT y respaldos HTTP permanecen bloqueados. Sin cambios en IA, firmware o datos originales; sin commit/push. SaaS-07 no iniciado.
