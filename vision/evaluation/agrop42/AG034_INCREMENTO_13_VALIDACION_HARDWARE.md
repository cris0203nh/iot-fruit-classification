# AG-034 — Incremento 13: entrega para validación de hardware objetivo

## Alcance

Se **prepara el trabajo que requiere hardware físico**, sin atribuirlo al desarrollador que no dispone del equipo. Arquitectura v1: **PC local + FastAPI + cámara RGB** para visión; **ESP32 + HX711** para peso. La prueba de rendimiento del Incremento 10 comparó únicamente *mango vs tomate* con imágenes de fuentes externas: no valida etiquetas de defectos E0/E1/E2, ni tiempos de captura con cámara.

**Ninguna prueba física se da por realizada en este incremento.** El CSV y los informes son registros declarativos cuyo respaldo debe revisarse; el SHA-256 acredita integridad de archivos, no autenticidad física, firma ni exactitud agronómica.

## 1. Preparar la plantilla (en el equipo de desarrollo)

Desde la raíz `iot-fruit-classification`:

```powershell
$python = '.\backend\.venv\Scripts\python.exe'
$base = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas"
$trabajo = "$base\AG034_Hardware_13_01"
& $python -m vision.evaluation.agrop42.validacion_hardware_ag034 plantilla --salida "$trabajo"

# Comprobación no física de FastAPI y especificaciones del equipo ejecutor.
# El perfil es opcional, pero se recomienda utilizar el obtenido en el Incremento 10.
& $python -m vision.evaluation.agrop42.validacion_hardware_ag034 diagnosticar `
  --api-url 'http://127.0.0.1:8000/api/health' `
  --perfil "$base\AG034_Recursos_10_01\AG034_perfil_recursos.json" `
  --salida "$base\AG034_Diagnostico_13_01.json"
```

Si el backend no está levantado, `api_ok=false` es **diagnóstico de conexión**, no un fallo de test del proyecto. No se sobrescriben archivos existentes: usar sufijo `_02` al repetir. El diagnóstico registra SO, CPU lógicas, RAM física declarada por el sistema y hash del perfil de recursos; **no** certifica que sea el hardware final ni mide la RAM máxima durante inferencia.

## 2. Guía mínima para el compañero con hardware

### A. PC + cámara: cuatro pruebas obligatorias AG-034

| ID | Acción real | Evidencia requerida |
|---|---|---|
| VIS-01 | Registrar CPU, RAM, SO, versión Python y cámara del **equipo objetivo**; ejecutar `diagnosticar` | JSON diagnóstico + foto/ficha de PC y cámara |
| VIS-02 | Ejecutar `perfil_recursos_ag034` con el mismo ZIP y mismas repeticiones | `AG034_perfil_recursos.json`, salida y configuración |
| VIS-03 | Definir previamente límite p95 de procesamiento por vista y límite de RSS máxima; medir ambos y comparar | CSV de muestreo de RSS, perfil p95 y límites con fecha de aprobación |
| VIS-04 | Capturar una fruta **con la cámara real**, asociar foto a ID, procesar con FastAPI y demostrar el flujo | Foto original + registro de asociación/captura + respuesta del sistema |

El objetivo de **menos de 2 segundos por fruto** discutido previamente fue una *meta provisional de diseño*, no requisito aprobado ni resultado observado. La decisión de umbrales debe quedar fechada ANTES de realizar las mediciones. No sustituir `tracemalloc` por RSS: `tracemalloc` solo mide asignaciones Python, el Working Set incluye memoria residente del proceso.

Para medir RSS del proceso de comparación en Windows (desde la raíz del proyecto):

```powershell
$python = '.\backend\.venv\Scripts\python.exe'
$zip = "$env:USERPROFILE\Downloads\AgroScan_Dataset_30_Frutos_90_Vistas.zip"
$salida = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas\AG034_RSS_13_01"

.\vision\evaluation\agrop42\AG034_Medir_RSS_Windows.ps1 `
  -Python $python -Zip $zip -Salida $salida -IntervaloMs 100
```

El script crea `benchmark/AG034_perfil_recursos.json`, `muestras_rss.csv`, `AG034_RSS_resultado.json` y logs. El monitoreo se limita al proceso de benchmark y puede subestimar picos por muestreo. Se debe registrar además hardware/OS, número de ejecuciones, condiciones de carga y discrepancias. **El script PowerShell no fue ejecutado aquí por falta de Windows; requiere validación en el equipo real.**

### B. ESP32/HX711: tres pruebas complementarias de integración

Son útiles para la demostración del MVP y para AGROP-21/22/23, pero **no sustituyen** los requisitos de visión del AG-034.

1. Registrar el **modelo de placa, conexión, puerto COM y firmware real**; fotografiar el montaje. No basta el simulador.
2. Comprobar sin pesos que la balanza funciona; realizar tara solo con plataforma vacía. Registrar calibración con masa de referencia, valor esperado, valor observado y error. No declarar estabilidad o precisión sin medición repetida.
3. Desde la raíz del repositorio, con FastAPI encendido, ejecutar el puente serial (cambiar `COM3` por el puerto real):

```powershell
.\backend\.venv\Scripts\python.exe -m firmware.tools.serial_bridge `
  --port COM3 `
  --url http://127.0.0.1:8000/api/iot/measurements
```

**No utilizar `--allow-simulated` para acreditar hardware físico.** El puente rechaza mediciones simuladas por defecto. Ejecutar `--tare-on-open` solo cuando se confirme físicamente plataforma vacía. Registrar el ACK `{received: true}` y comprobar `GET http://127.0.0.1:8000/api/iot/status` durante una lectura reciente, sin confundir el dato del simulador con una medida real.

Para iniciar el backend, en una terminal independiente:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

El frontend React no mide recursos del ESP32. Toda prueba de presencia, conectividad y calibración requiere evidencia del equipo de tu compañero.

## 3. Cómo registrar el trabajo

Abrir `AG034_registro_pruebas.csv` dentro de la carpeta `$trabajo`. **No modificar** `prueba_id` ni `alcance`. Para cada prueba ejecutada:

- `estado`: `aprobada`, `fallida`, `bloqueada` o `no_aplica` (solo complementarias).
- `equipo_id`, `responsable`, `fecha_iso` con zona horaria (`2026-11-05T22:00:00-05:00`), `observaciones`.
- `criterio_predefinido`: criterio escrito y acordado **antes** de la prueba.
- `evidencia_relativa`: ruta a documento no vacío bajo `evidencias/`, por ejemplo `evidencias/VIS-02_perfil.json`.
- Para `VIS-03`, registrar `limite_ms`, `resultado_ms` (p95), `limite_mib` y `resultado_mib` (RSS máxima). Si se superó un límite no se puede marcar `aprobada`.

Las pruebas obligatorias `VIS-*` no admiten `no_aplica`. El estado `pendiente` permanece sin evidencia acreditada; las pruebas `IOT-*` son complementarias y no determinan el cierre AG-034 de visión.

## 4. Generar informe auditable

```powershell
$python = '.\backend\.venv\Scripts\python.exe'
$base = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas"
$trabajo = "$base\AG034_Hardware_13_01"
$informe = "$base\AG034_Hardware_13_Auditoria_01"

& $python -m vision.evaluation.agrop42.validacion_hardware_ag034 auditar `
  --carpeta "$trabajo" --salida "$informe"

& $python -m vision.evaluation.agrop42.validacion_hardware_ag034 verificar `
  --salida "$informe" --carpeta "$trabajo"
```

La auditoría guarda una copia del CSV, JSON, informe Markdown y manifiesto SHA-256; la verificación comprueba la copia, el informe, el CSV original y las evidencias **si se pasa `--carpeta`**. El resultado `documentacion_fisica_presentada_sujeta_a_revision` no es acreditación automática del hardware: requiere revisar las evidencias y aceptar los criterios.

## 5. Falta para cerrar AG-034

- Revisar independientemente las evidencias físicas y la correspondencia entre el equipo evaluado y la arquitectura destino.
- Definir y verificar umbrales en la PC objetivo (y cámara si forma parte del flujo operativo).
- Resolver por separado el objetivo de *calidad externa E0/E1/E2*: las 90 vistas externas carecen de etiquetas comerciales acreditadas y las fotografías de mango son Ataulfo, no Kent. Alternativamente, obtener aceptación **formal y documentada** del docente para un alcance reducido. Este módulo no produce esas etiquetas ni declara cierre.

**Criterio honesto de cierre:** software preparado + evidencias físicas revisadas + etiquetas/alcance aprobado + decisión final documentada. No mover Jira a `Done` solo por tener un CSV en `aprobada`.
