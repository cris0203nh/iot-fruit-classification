# SaaS-08 — Cierre técnico

**Dictamen:** software preparado para un piloto controlado condicionado a activación y comprobación física. No habilitar todavía el piloto real ni declarar preparación comercial. Solo se cambiaron pruebas y este documento; originales, credenciales, IA y firmware intactos.

| Área | Estado | Evidencia / condición |
|---|---|---|
| Migración y recuperación en copia actualizada | APROBADO | `s006identity` → `s007iot`, upgrade repetido, downgrade, respaldo verificado y restauración. 23 tablas históricas, tres usuarios, propietario existente, 35 referencias de imagen y hashes de 86 archivos conservados. FK/integridad correctas. |
| Roles, propietario, membresías, selección y revocación | APROBADO | A/B con administrador, operador y revisor; permisos retirados con JWT ya emitidos. |
| Google e invitaciones: controles técnicos | APROBADO | Firmas RSA/claims/nonce, vinculación explícita, vencimiento, uso único, revocación y aislamiento. Google real sigue pendiente. |
| Operación A/B y almacenamiento | APROBADO | Captura, revisión, historial, CSV con hash, fotos/descargas, exportación lógica, dispositivos y mediciones. Bridge contra FastAPI por HTTP local real; telemetría sintética. Reenvíos, rotación, revocación y concurrencia DELETE/WAL. |
| Compatibilidad del clasificador | APROBADO | YOLO local en CPU y decisiones SVC locales de mango/tomate sobre imágenes sintéticas. No se cambiaron modelos ni algoritmos. Esto no mide exactitud E0/E1/E2. |
| Activación real IoT | BLOQUEADO | Original aún en `s006identity`; cero administradores empresariales activos. Falta migrar, crear un administrador empresarial y aprovisionar el dispositivo histórico, importado sin secreto e inactivo. |
| OAuth y revisión privada de propuestas SVC | BLOQUEADO | Faltan `AGROSCAN_GOOGLE_CLIENT_ID` y `AGROSCAN_REVIEW_RUN`. La revisión humana trazable en SQLite sí pasó; el flujo privado externo completo no está acreditado. |
| Hardware, HTTPS de despliegue y exactitud experimental | PENDIENTE | ESP32/báscula: tara, calibración, estabilidad, reinicio; cámara RGB y fruta reales; despliegue HTTPS; evaluación independiente con referencias humanas verificadas. No hay métricas nuevas de exactitud. |
| Restauración HTTP global | BLOQUEADO | Bloqueo deliberado 503 conservado. Mantenimiento privado probado únicamente en copia. Exportación empresarial no equivale a respaldo restaurable. |

Pruebas ejecutadas: **243 Python: 241 aprobadas, dos omitidas** (symlinks Windows; entrenamiento opcional con sklearn ausente). Incluyen regresiones SaaS-02–07, dos pruebas integrales nuevas `test_saas08_pilot.py`, contratos SVC/V2 y métricas con datos sintéticos. **161 frontend: 160 aprobadas, una omitida** por falta de evidencia React de inferencia real grabada. Se ejecutaron `npm test`, seguridad JWT y revisión. Build/lint aprobados; aviso no bloqueante de bundle >500 kB. La prueba antigua SaaS-02 fallaba al llamar IoT sin identidad: se actualizó su fixture para autenticar el dispositivo y sincronizar antes del bloqueo; no se relajaron controles.

## Comandos de activación — ejecutar manualmente

Desde la raíz, **con API, workers y bridges detenidos**. El destino explícito es la base actual `backend/data/agroscan.db`. El primer comando crea un respaldo global privado y verifica su restaurabilidad en temporales; si falla, no migrar:

```powershell
Push-Location .\backend
try {
    $env:AGROSCAN_DATA_DIR = (Resolve-Path .\data).Path
    $env:AGROSCAN_DATABASE_URL = 'sqlite:///' + $env:AGROSCAN_DATA_DIR.Replace('\', '/') + '/agroscan.db'
    @'
import tempfile
from pathlib import Path
from app.services.backup_service import BACKUP_DIR, create_backup, prepare_restore
backup = create_backup()
with tempfile.TemporaryDirectory(prefix='verify-', dir=BACKUP_DIR) as target:
    prepare_restore(Path(backup['path']), Path(target))
print('Respaldo verificado:', backup['path'])
'@ | & .\.venv\Scripts\python.exe -
    if ($LASTEXITCODE -ne 0) { throw 'Respaldo no verificado; no migrar.' }
    & .\.venv\Scripts\python.exe -m alembic upgrade s007iot
    if ($LASTEXITCODE -ne 0) { throw 'Migración fallida; no iniciar la operación.' }
    & .\.venv\Scripts\python.exe -m alembic current
} finally { Pop-Location }
```

Reiniciar la API con su configuración habitual. El propietario debe crear **una cuenta empresarial administradora nueva** desde el panel existente; no promover automáticamente a cuentas históricas. No usar el privilegio global como credencial IoT. Configurar Google y el directorio privado externo según SaaS-06/07 antes de habilitar esos flujos.

Desde la raíz, registrar una estación/dispositivo nuevos en la empresa piloto y arrancar el bridge. Ejecutar después de crear la empresa y su administrador en el panel del propietario. Las solicitudes no imprimen JWT ni secretos; consultar los listados antes de repetir un alta:

```powershell
$api = 'http://127.0.0.1:8000'
$businessLogin = Get-Credential -Message 'Cuenta administradora empresarial'
$session = Invoke-RestMethod -Method Post -Uri "$api/api/auth/login" -ContentType 'application/x-www-form-urlencoded' -Body @{
    username = $businessLogin.UserName; password = $businessLogin.GetNetworkCredential().Password
}
$businessHeaders = @{ Authorization = "Bearer $($session.access_token)" }
Invoke-RestMethod -Uri "$api/api/auth/organizations" -Headers $businessHeaders | Format-Table id,name,roles
$businessHeaders['X-Organization-ID'] = Read-Host 'ID de empresa autorizada'
Invoke-RestMethod -Uri "$api/api/iot/stations" -Headers $businessHeaders | Format-Table id,code,name,isActive
Invoke-RestMethod -Uri "$api/api/iot/devices" -Headers $businessHeaders | Format-Table id,deviceId,stationId,isActive,provisioned
$stationBody = @{ code = (Read-Host 'Código de estación NUEVA'); name = (Read-Host 'Nombre de estación') } | ConvertTo-Json
$station = Invoke-RestMethod -Method Post -Uri "$api/api/iot/stations" -Headers $businessHeaders -ContentType 'application/json; charset=utf-8' -Body $stationBody -ErrorAction Stop
$deviceBody = @{ stationId = $station.id; deviceId = (Read-Host 'device_id exacto emitido por el ESP32') } | ConvertTo-Json
$provision = Invoke-RestMethod -Method Post -Uri "$api/api/iot/devices" -Headers $businessHeaders -ContentType 'application/json' -Body $deviceBody -ErrorAction Stop
$env:AGROSCAN_DEVICE_TOKEN = $provision.credential
try {
    & .\backend\.venv\Scripts\python.exe .\firmware\tools\serial_bridge.py --port COM3 --url "$api/api/iot/measurements"
} finally {
    Remove-Item Env:AGROSCAN_DEVICE_TOKEN -ErrorAction SilentlyContinue
    Remove-Variable provision,session,businessHeaders,businessLogin -ErrorAction SilentlyContinue
}
```

Seleccionar el puerto físico correcto; `deviceId` de telemetría debe coincidir con el registro. Para una estación/dispositivo nuevo, usar los POST autenticados documentados en [SaaS-07](SAAS-07.md), sin duplicar históricos. Remoto: HTTPS obligatorio; el bridge rechaza HTTP no local y redirecciones. Tras activar, verificar físicamente cada estación y repetir la aceptación A/B en el despliegue antes de admitir clientes.

## Primera activación: orden y aceptación

1. Revisar el checkpoint local de código seleccionado en `.agroscan-checkpoints/`: sin commit ni cambios al índice. Git ya contiene **51 fotos y cuatro SQLite**; el ZIP no los incluye. No publicar el repositorio/historial sin saneamiento autorizado. No usar `git add .`.
2. Respaldo privado preparado y verificado: ZIP y archivo SHA-256 locales en `backend/data/backups/`. Fuente abierta en solo lectura, originales sin cambios durante la verificación; migración/repetición/reversión/restauración solo en copia. Como había API activa, **renovar el respaldo en mantenimiento** mediante el bloque anterior antes de migrar.
3. Detener API/workers/bridges, ejecutar ese bloque y exigir `alembic current = s007iot`. Reiniciar API. No se ha ejecutado esta migración en la base original.
4. Propietario: acceso tradicional → panel Empresas → registrar la empresa real → crear administrador empresarial nuevo (usuario/nombre elegidos y contraseña privada de al menos 12 caracteres). Conservar «AgroScan Inicial» y sus históricos. Verificar que la nueva empresa está activa y el administrador no tiene privilegio global. No reutilizar/promover cuentas históricas automáticamente.
5. Iniciar sesión como ese administrador mediante el bloque anterior, seleccionar su empresa autorizada y registrar la estación/dispositivo nuevos. No imprimir `$provision`: contiene el secreto de entrega única.

Un dispositivo físico debe pertenecer a una sola empresa operativa; no reutilizar simultáneamente su bridge/credencial para otra. La estación nueva no debe reutilizar los registros históricos de la empresa inicial. Antes de repetir un alta, consultar `/api/iot/stations` y `/api/iot/devices` para evitar duplicados. La credencial solo queda en memoria/entorno del bridge, no en Git, URL, firmware ni logs. Si se pierde, rotarla; no hay consulta posterior del secreto.

Google real: crear cliente OAuth **Web**, autorizar origen exacto local o HTTPS real, configurar `AGROSCAN_GOOGLE_CLIENT_ID` en el entorno privado del backend y reiniciarlo; sin client secret en React ni tarjeta. Probar acceso tradicional → vinculación explícita con contraseña → Google → cambio/revocación de membresía. Sin enlace/invitación autorizado, la coincidencia de correo debe denegarse. Ver [configuración SaaS-06](SAAS-06.md). Para revisión privada SVC, configurar `AGROSCAN_REVIEW_RUN` en directorio privado persistente fuera del repositorio; probar permisos antes de habilitar ese flujo.

| Etapa mínima | Sin hardware | Criterio para aceptar / avanzar |
|---|---|---|
| Respaldo/migración | Sí, copia actualizada | ZIP restaurable, IDs/filas/hashes iguales, integridad/FK correctas; solo después, mantenimiento manual. |
| Empresa/roles | Sí, empresas sintéticas A/B | Administrador/operador/revisor autorizados; recursos ajenos 403/404; token previo pierde permisos revocados. |
| Bridge/IoT | Sí, telemetría sintética aislada | Credencial válida 200; reenvío sin nueva fila ni fecha; credencial ausente/revocada 401; rotación invalida la anterior. No inyectar mediciones sintéticas en datos históricos. |
| Báscula y ESP32 | **No** | Plataforma vacía/tara, masa de referencia y calibración registrada; estable/inestable correctos, última lectura propia, reinicio/reenvío sin mezcla ni duplicación. Registrar tolerancia del protocolo antes de medir. |
| Cámara y flujo completo | **No**, para aceptación física | Crear lote exclusivo de prueba en empresa piloto y fotografiar objeto/fruta de ensayo: dos capturas, pesos pre/post coherentes, confirmación, revisión humana, descarga con mismo SHA-256 y reporte trazable. No tocar lotes históricos. |
| Aislamiento desplegado y cierre | Parcial | A no lee/modifica/descarga B; revocar dispositivo y membresía retira acceso; restauración HTTP sigue 503. Google real requiere configuración/cuenta; exactitud E0/E1/E2 requiere ensayo independiente con etiquetas humanas, no solo este recorrido. |

Conservar el lote de ensayo identificado como prueba y el registro de resultados; no borrar ni reclasificar históricos para limpiar la demostración. Un fallo de aislamiento, integridad o revocación detiene el piloto. Hardware, OAuth real, HTTPS y evidencia experimental siguen pendientes; no declarar preparación comercial.
