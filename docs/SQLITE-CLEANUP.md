# Limpieza SQLite por alcance aprobado

Herramienta: `tools/agroscan_cleanup.py` (stdlib, sin importar FastAPI ni cargar `.env`). Resuelve `AGROSCAN_DATA_DIR/agroscan.db`; sin esa variable usa `backend/data/agroscan.db`, como el backend. Nunca crea otra base ni ejecuta migraciones. Usar el mismo entorno que la API y confirmar la ruta mostrada. Los inventarios privados y respaldos no se guardan en Git.

## Inventario y dry-run

Desde la raíz, con un directorio privado **nuevo o vacío fuera del repositorio**:

```powershell
$privateRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AgroScan-Private-Backups'
$inventoryOut = Join-Path $privateRoot ('inventory-' + [guid]::NewGuid().ToString('N'))
& .\backend\.venv\Scripts\python.exe tools/agroscan_cleanup.py --out $inventoryOut
```

Genera `inventory.json` (tablas, FK, cantidades, identificadores no secretos, hashes de filas, operadores sin membresías y rutas/SHA-256 de fotos), `agroscan-before.sqlite`, `backup-verification.json`, copias de imágenes referenciadas, `dry-run.json` y `plan-empty.json`. Comprueba integridad/FK y coincidencia de todas las filas del respaldo. No imprime hashes de contraseña, tokens ni identidades Google; sus claves sensibles se seleccionan por hash de fila. Un nombre/fecha nunca convierte una fila en descartable.

Si Python carece de permiso para escribir fuera del proyecto, se detiene; no cambiar el destino al repositorio ni ejecutar borrados sin respaldo privado verificable. En la sesión de inventario se utilizó PowerShell para guardar una instantánea SQLite consistente obtenida en memoria y copiar/verificar fotos, manteniendo la fuente en solo lectura.

## Preparar el alcance después de la revisión del usuario

Copiar `plan-empty.json` a `plan-reviewed.json` en la carpeta privada. Conservar `database` y `database_digest`. Incluir **solo** filas cuya procedencia y retirada hayan sido confirmadas; cada entrada usa el hash exacto de `inventory.json`:

```json
{
  "table": "measurements",
  "row_sha256": "HASH_EXACTO_DE_LA_FILA_REVISADA",
  "evidence": {"kind": "user_confirmed", "detail": "Origen comprobado y autorización explícita del usuario"}
}
```

No basta seleccionar un lote: deben revisarse y enumerarse individualmente sus dependientes. La herramienta ordena hijos antes que padres y comprueba las referencias diferidas; no añade cascadas al plan automáticamente. Solo acepta tablas operativas/comerciales enumeradas. Empresas, membresías, roles, estaciones/dispositivos, planes, propietario y migraciones quedan protegidos. Todas las filas no seleccionadas, incluidas las históricas y cuentas restantes, deben quedar idénticas.

Para retirar una cuenta: como máximo un usuario cuyo único rol sea operador, sin ninguna membresía (también cuentan las inactivas), sin privilegio de propietario y sin referencias históricas en cualquier FK. Enumerar también sus filas exactas de `user_roles`/`google_identities`; no se pueden eliminar relaciones de autenticación de otra cuenta. Invitaciones y desafíos globales no se purgan por inferencia. Si no existe tal cuenta, no seleccionar ninguna.

```powershell
$plan = Join-Path $inventoryOut 'plan-reviewed.json'
$dryOut = Join-Path $privateRoot ('dry-run-' + [guid]::NewGuid().ToString('N'))
& .\backend\.venv\Scripts\python.exe tools/agroscan_cleanup.py --plan $plan --out $dryOut
```

El borrado de ensayo ocurre **solo en memoria**, con rollback. La consola muestra las filas seleccionadas y `dry-run.json` informa cantidades. Cualquier cambio de la base desde el inventario invalida el plan: repetir inventario y revisión, sin actualizar hashes a ciegas.

## Ejecución futura — requiere autorización expresa del alcance

Detener API, bridges y workers en mantenimiento; no hacerlo automáticamente. Tras aprobar el inventario/dry-run y la lista exacta de filas:

```powershell
$planSha = (Get-FileHash -LiteralPath $plan -Algorithm SHA256).Hash.ToLower()
$executeOut = Join-Path $privateRoot ('execution-' + [guid]::NewGuid().ToString('N'))
& .\backend\.venv\Scripts\python.exe tools/agroscan_cleanup.py --plan $plan --out $executeOut `
  --execute --maintenance-confirmed --confirm-plan-sha256 $planSha
```

No se ha ejecutado este bloque sobre datos reales. `BEGIN IMMEDIATE` impide escrituras simultáneas; se exige un nuevo respaldo íntegro y completo de fotografías antes de borrar. Cada `DELETE` filtra la PK completa y debe afectar una fila. Antes de commit se comparan todas las filas restantes y el esquema, se ejecutan `integrity_check`/`foreign_key_check` y se guarda evidencia previa. Fallos antes de commit producen rollback. `execution.json` confirma commit y cantidades por tabla; `failure.json` distingue rollback de un fallo al emitir reporte después de un commit ya realizado. No interpretar únicamente el código de salida sin revisar estos informes.

**Los archivos físicos se conservan siempre**, incluso al retirar su referencia SQLite; no hay `unlink`, purga de carpetas, `VACUUM`, reinicio de secuencias ni restauración automática. Conservar respaldos privados: contienen datos de autenticación y evidencia. No usar restauración HTTP global.

Verificación del procedimiento (solo fixtures sintéticas):

```powershell
& .\backend\.venv\Scripts\python.exe -m unittest discover -s tests -p test_agroscan_cleanup.py -v
```

Resultado local: **12 pruebas aprobadas**, sin omisiones. No se necesitan build frontend ni cambios de workflows para este mantenimiento privado.
