# Sincronización con la laptop de hardware

**Publicación bloqueada hasta completar el saneamiento autorizado del historial.**
No usar esta guía para asumir que los cambios locales ya están en `main`.

## Código y entorno

Después del saneamiento, hacer un clon nuevo; no mezclar el historial antiguo:

```powershell
git clone https://github.com/cris0203nh/iot-fruit-classification.git AgroScan
Set-Location AgroScan
git status
git rev-parse HEAD
py -3.13 -m venv "$env:USERPROFILE\Documents\AgroScan-Python-Probe"
$py = "$env:USERPROFILE\Documents\AgroScan-Python-Probe\Scripts\python.exe"
& $py -m pip install -r backend/requirements.txt
& $py -m pip install -r vision/requirements-dev-cpu.txt -r firmware/tools/requirements.txt
& $py -m pip check
npm --prefix frontend ci
```

Python 3.13 se probó localmente; CI usa 3.12 para las suites principales. El
archivo CPU fija Torch/Torchvision para DEV: confirmar disponibilidad de ruedas
para el intérprete elegido. Frontend requiere Node.js compatible con
`frontend/package.json` y el Vite instalado; se comprobó Node 24.19.0 localmente o la versión
22 compatible de CI. Vite exige `^20.19.0 || >=22.12.0` según su paquete instalado.
No versionar el venv ni `node_modules`.

## Datos, identidad y configuración

- Cada laptop mantiene su propia SQLite, fotos, respaldos, sesiones y secretos.
  **Nunca copiar la base de una laptop para reemplazar la de otra.**
- Las guardas actuales de DEV esperan `Documents/AgroScan-Dev` del usuario local,
  no una ruta `C:\Users\Luigi`. No copiar `jwt.clixml`: DPAPI está ligado a la
  identidad Windows. Preparar la instancia y cuentas mediante los procedimientos
  privados existentes, sin credenciales predeterminadas ni promoción automática.
- No iniciar contra `backend/data/agroscan.db` por omisión. Definir explícitamente
  `AGROSCAN_DATA_DIR` y `AGROSCAN_DATABASE_URL` hacia el directorio privado acordado.
- Migraciones: detener API/bridge, respaldo consistente y verificado, probar en
  copia desechable y ejecutar Alembic con destino explícito. La revisión local
  prevista es `c017catalog`; el arranque no la aplica automáticamente.
- `AGROSCAN_JWT_SECRET` debe ser local y privado. Google es opcional: configurar
  `AGROSCAN_GOOGLE_CLIENT_ID` en backend y autorizar el origen exacto en Google.
  No incluir Client Secret, contraseñas o claves SMTP en Git. Sin OAuth real,
  conservar el login tradicional. SMTP permanece opcional.

## Modelos (separados de fotografías privadas)

Ya versionados, conservar sin reemplazo:

| Recurso | SHA-256 |
|---|---|
| `vision/models/yoloe-26n-seg.pt` | `1741c1f8da3cea47e2c01829c334a50dc0b9bbd05e685b90a3ce84fae32c8c1b` |
| `vision/models/agroscan_mango_tomato_prompts.npz` | `94e76edd62c4c11ec2a2b72d3b9927d8cf1ffd87b435edc021785a0faa151a65` |

Instalación privada pendiente: los JSON V2 existentes y su manifiesto, **sin
fotografías ni datasets**. No regenerarlos ni reentrenar para instalar:

| Artefacto | SHA-256 |
|---|---|
| `ag055_v2_mango.json` | `17b59e4faf1b183d263107789cdfdb881b040899a1b335a9610454f427fac2f4` |
| `ag055_v2_tomate.json` | `113957046c1c16e50d42e8bc79203322b2ed733b16d601497ce17dda04e2aa7f` |

DEV espera `data/ag055_v2/models` dentro de su raíz privada y `SHA256SUMS.json`
en `data/ag055_v2`; también admite `AGROSCAN_V2_MODELS_PATH`. Verificar los hashes
con `Get-FileHash -Algorithm SHA256`. Distribuir solo mediante un canal privado
autorizado; su disponibilidad no queda resuelta al clonar el código.

## Arranque y comprobaciones físicas pendientes

Dos terminales desde la raíz, una por servicio:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_dev.ps1 -Action backend
```

```powershell
npm --prefix frontend run dev
```

Abrir `http://localhost:5173/acceso`; no alternarlo con `127.0.0.1` para cookies.
QA (8778/5188), DEV (8000/5173) y hardware mantienen configuración independiente.

Conectar la cámara RGB, conceder permiso al navegador y comprobar la cámara
seleccionada. Enumerar puertos seriales con `& $py -m serial.tools.list_ports`.
El puerto COM cambia entre laptops; cerrar monitores seriales que lo ocupen.
Primero comprobar ESP32 sin envío: `& $py firmware/tools/serial_bridge.py --port COMx`.
Después de aprovisionar estación/dispositivo en la organización correcta,
configurar `AGROSCAN_DEVICE_TOKEN` privadamente y añadir
`--url http://127.0.0.1:8000/api/iot/measurements`. No usar JWT de usuario como
credencial IoT; si DEV rechaza el bridge por su guarda de origen, diagnosticar
esa integración antes de habilitarla, sin desactivar controles.

Tara solo con plataforma vacía; calibrar la balanza con masas verificadas y el
procedimiento existente. ArUco exige el patrón, impresión y tamaño reales
declarados: no inferir cm desde px sin calibración válida. Capturar dos vistas
reales, verificar detección, geometría, propuesta preliminar y revisión humana.
Estas pruebas físicas, OAuth real y exactitud E0/E1/E2 siguen pendientes.
