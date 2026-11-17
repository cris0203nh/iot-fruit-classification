# SaaS-07 — IoT y almacenamiento

- `s007iot` añade estaciones/dispositivos empresariales y FK compuesta de mediciones a `(organization_id, device_id)`. Conserva filas e IDs históricos; registra sus dispositivos **inactivos y sin credencial**. Repetir upgrade no duplica. Downgrade rechaza dispositivos aprovisionados o estaciones modificadas.
- Ingreso IoT: Bearer individual aleatorio de 256 bits, solo SHA-256 en SQLite, entrega única, rotación y revocación. No acepta JWT humano, empresa en cabecera ni identificador de otro dispositivo. Empresa derivada exclusivamente de la identidad autenticada; estación y empresa deben estar activas. Autenticación/escritura y revocación se serializan con `BEGIN IMMEDIATE`.
- Estado y pesajes: JWT/membresía vigentes, lecturas exclusivamente de la empresa y dispositivos/estaciones activos. Idempotencia, fechas originales y validación del pesaje conservadas. Sin `s007iot`, las rutas IoT continúan cerradas con 503.
- Capturas nuevas: `images/organizations/{empresa}/E-{evaluación}/`. Referencias antiguas conservadas. Descargas y consumidores de evidencia verifican pertenencia, ruta, tamaño, contención y enlaces/junctions. Revisión privada externa: la organización inicial conserva su directorio histórico; las nuevas usan subdirectorios empresariales, evitando búsquedas compartidas por hash.
- Exportación lógica: `GET /api/organization/export`, solo administrador de la empresa activa. ZIP con datos permitidos, fotografías referenciadas y manifiesto SHA-256; sin SQLite, contraseñas, identidades OAuth, invitaciones ni credenciales/tokens de acceso. Snapshot consistente, liberado antes de comprimir para no bloquear mediciones; límites de tamaño y rechazo de evidencia faltante. **No es un respaldo restaurable**: no incluye modelos globales ni archivos privados de revisión externos a SQLite.
- Respaldos y restauración HTTP globales siguen en 503. Mantenimiento privado existente conservado; debe ejecutarse sin procesos de la aplicación escribiendo. No hay restauración empresarial HTTP.

## Activación manual

No se migraron datos originales ni se crearon secretos reales. En mantenimiento, detener aplicación/bridges, realizar y verificar el respaldo privado existente y aplicar desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Con JWT y contexto empresarial autorizados, el administrador utiliza:

| Operación | Endpoint |
|---|---|
| Consultar/crear estación | `GET/POST /api/iot/stations` (`code`, `name`) |
| Suspender/reactivar estación | `PATCH /api/iot/stations/{id}` (`isActive`) |
| Consultar/registrar dispositivo | `GET/POST /api/iot/devices` (`stationId`, `deviceId`) |
| Aprovisionar histórico o rotar secreto | `POST /api/iot/devices/{id}/credentials` |
| Revocar credencial | `DELETE /api/iot/devices/{id}/credentials` |

`deviceId` debe coincidir con la telemetría existente. Suspender una estación revoca sus credenciales; reactivarla exige aprovisionarlas nuevamente. Los listados nunca muestran secretos/hashes. No se añadió un panel nuevo.

El bridge necesita `AGROSCAN_DEVICE_TOKEN` en su entorno privado, sin incluirlo en argumentos, URL, repositorio o registros. Desde la raíz, introducirlo sin mostrarlo ni guardarlo en el historial:

```powershell
$deviceSecret = Read-Host 'Credencial del dispositivo' -AsSecureString
$env:AGROSCAN_DEVICE_TOKEN = [System.Net.NetworkCredential]::new('', $deviceSecret).Password
try {
    & .\backend\.venv\Scripts\python.exe .\firmware\tools\serial_bridge.py --port COM3 --url http://127.0.0.1:8000/api/iot/measurements
} finally {
    Remove-Item Env:AGROSCAN_DEVICE_TOKEN
    $deviceSecret.Dispose()
}
```

Ambos bridges envían Authorization; el envío remoto exige HTTPS y no sigue redirecciones. Firmware ESP32 y algoritmos/modelos sin cambios; cámara RGB y registro automático mantienen autenticación humana y contratos actuales.

## Verificación y límites

- Copia aislada de la base actual, abierta inicialmente en modo solo lectura: respaldo, upgrade repetido, downgrade y restauración verificados. **23 tablas históricas y hashes de 86 fotografías intactos**, incluidos propietario y hashes de contraseña. Integridad/FK correctas; cero credenciales automáticas.
- Regresión: 200 pruebas backend aprobadas y una omitida por permisos de symlink en Windows; seis pruebas frontend IoT aprobadas. A/B, autenticación, revocación concurrente, reenvíos simultáneos, pesaje, fotos, exportación durante ingreso, permisos, migración, Google/invitaciones y respaldo/restauración. `git diff --check` correcto; frontend sin cambios, sin build/lint adicionales.
- No se acredita hardware físico. Los directorios privados de revisión mantienen su restricción de estar fuera del repositorio: este entorno denegó temporales externos, por lo que se verificó el aislamiento del resolvedor y el rechazo de configuración ausente, sin completar el flujo HTTP de revisión privada con almacenamiento externo.
- Pendiente operativo: respaldo/migración real, aprovisionamiento por administrador y prueba física con cada estación. SQLite mantiene un escritor; ante bloqueo, el ingreso responde 503 para reintento idempotente.

Archivos nuevos: `iot_models.py`, `s007iot_saas07.py`, servicios `device_auth.py`, `evidence_storage.py`, `organization_export.py`, routers `iot_admin.py`, `organization_export.py`, pruebas `test_saas07_*`. Ajustados registro de modelos/rutas, IoT, lectores de fotografías/revisión, ambos bridges y fixtures/pruebas relacionadas. Sin dependencias nuevas, commit, push ni SaaS-08.
