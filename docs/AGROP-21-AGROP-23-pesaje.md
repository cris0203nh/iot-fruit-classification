# Pesaje ESP32 con simulación y preparación de calibración

## Alcance y trazabilidad

- **AGROP-21 / AG-013:** firmware ESP32-HX711, diagnóstico de disponibilidad, modo simulado explícito y salida serial. Montaje físico y lectura real siguen pendientes de verificación.
- **AGROP-23 / AG-015:** comandos de tara y calibración, cálculo de gramos, persistencia del factor y pruebas del procesamiento. No existen aún factor, exactitud ni repetibilidad obtenidos con la celda física.
- **AGROP-22:** Junior puede consumir los estados para preparar la visualización. **AGROP-24:** Josmely puede probar bloqueos ante errores. Estas contribuciones no dan por terminadas sus tareas.

Esta entrega se integra en `cris0203nh/iot-fruit-classification`. Se contrastó el puente con `docs/api-contract.md`, `backend/app/iot_schemas.py` y `backend/app/routers/iot.py`. Los identificadores se limitan a 64 caracteres según el esquema real. Las pruebas de integración ejecutan las rutas IoT del equipo con una base SQLite aislada; no acceden a datos de producción ni prueban todavía el montaje físico.

## Montaje y configuración

Componentes frente al observador y USB del ESP32 abajo: GPIO32 es el séptimo pin del lado izquierdo desde arriba; GPIO33, el octavo. Confirmar las etiquetas, no las filas de la protoboard.

| HX711 | ESP32 | Jumper |
| --- | --- | --- |
| VCC | 3V3 | Rojo |
| GND | GND | Negro |
| DT | GPIO32 | Verde |
| SCK | GPIO33 | Amarillo |

Celda utilizada: rojo E+, negro E−, blanco A−, verde A+. B+/B− libres. Este registro de colores debe verificarse para la celda concreta. Soldar uniones y comprobar continuidad; fijar un extremo de la celda a base rígida, dejar libre el extremo de carga y no comprimir la zona central. El firmware no arregla contactos eléctricos ni un montaje que impida la flexión.

Arduino IDE: placa **NodeMCU-32S**, ESP32 by Espressif Systems; librería **HX711 Arduino Library 0.7.5**, Bogdan Necula. Serial **115200** baudios y terminador nueva línea. `COM3` fue el puerto observado en las pruebas; puede cambiar.

## Ejecutar simulación en el ESP32

El sketch tiene `AGROSCAN_SIMULATION=1` por defecto. Usa muestras artificiales con offset 100000 y 100 cuentas/g. Estos valores son exclusivamente una fixture, nunca una calibración real, y no se guardan en NVS.

1. Cargar el sketch. No requiere HX711 para simular.
2. Abrir monitor serial a 115200 con nueva línea. Esperar al menos un segundo con peso simulado 0.
3. Enviar `TARE`. Se requiere cero explícito incluso en simulación.
4. Esperar un segundo: deberá aparecer estado `stable`, peso 0.
5. Enviar `WEIGHT 250`; tras llenar la ventana, deberá aparecer aproximadamente 250 g.
6. Enviar `NOISE ON`: aparece `unstable`. `NOISE OFF` recupera estabilidad tras llenar la ventana.
7. Enviar `DISCONNECT`: estado `sensor_unavailable` y `measurement:null`. `CONNECT` recupera muestras y exige llenar una nueva ventana.
8. Enviar `STATUS` para inspeccionar offset, factor y revisión.

Las medidas simuladas usan `simulated:true`, dispositivo `simulator-esp32-...` y versión `simulated-...`. No mostrarlas como resultados físicos en Jira o el informe.

## Ejecutar sensor real y calibración

Cambiar el `#define AGROSCAN_SIMULATION 1` por `0` y volver a cargar. La memoria de calibración real está separada de la fixture de simulación. En cada arranque se exige tara aun si existe un factor guardado.

1. Sin carga en plataforma y con lecturas crudas estables, esperar al menos un segundo y enviar `TARE`.
2. Si aún no hay factor, el estado seguirá `uncalibrated` aunque la tara haya sido aceptada.
3. Colocar una masa de referencia cuya masa en gramos esté verificada. Esperar estabilización; enviar, por ejemplo, `CAL 500` **solo si la masa real es 500 g**.
4. El factor se calcula como `(media cruda con masa − offset de tara) / masa en gramos`. Se admite factor negativo por polaridad del montaje.
5. `calibration_ok` indica cálculo aceptado. `calibration_saved` confirma almacenamiento NVS; `storage_error` exige corregir persistencia, no asumir guardado. `SAVE` permite reintentar guardar. No se informa persistencia exitosa sin comprobar el número de bytes escritos.
6. Retirar la masa, revisar retorno al cero y comprobar otras masas y posiciones. Registrar esperado/obtenido y varias repeticiones. El código no determina automáticamente la exactitud ni da por aprobada la verificación metrológica.
7. Una nueva tara durante la sesión cambia el offset en RAM; `SAVE` guarda el registro actualizado. Después de reiniciar siempre se exige otra tara con plataforma vacía.

La calibración se rechaza si falta cero, la ventana cruda está incompleta/inestable, la masa no es finita o está fuera de (0,5000], o la diferencia es menor de 1000 cuentas. Los valores iniciales de estabilidad (10 muestras, rango ≤2 g), rango crudo para tara/CAL (≤200 cuentas), banda de cero ±2 g, pausa máxima entre muestras 400 ms y timeout 1500 ms son **parámetros provisionales**: ajustar mediante ensayos reales. No equivalen a exactitud de ±2 g.

## Estados y datos

No se publica medición válida hasta disponer de calibración, cero y ventana completa de muestras recientes. Saturación ADC y tiempo sin datos invalidan la ventana; la reconexión empieza una ventana nueva. Nunca se reutiliza un peso antiguo como si fuera nuevo ni se sustituye un error por una medición de cero.

| Estado | Significado | Confirmación en la aplicación |
| --- | --- | --- |
| sensor_unavailable | Sin muestras recientes, fallo simulado o ADC saturado | Bloquear |
| uncalibrated | Factor inexistente/inválido | Bloquear |
| zero_required | Falta tara del arranque actual | Bloquear |
| warming_up | Ventana insuficiente | Bloquear |
| out_of_range | Peso fuera del rango admitido | Bloquear |
| unstable | Peso calculado pero inestable | Bloquear |
| stable | Lectura reciente y estable según parámetros provisionales | Aplicar además las reglas del flujo de evaluación |

El timeout detecta ausencia de datos, pero no identifica todas las fallas eléctricas: una entrada averiada o desconectada que entregue valores constantes puede aparentar estabilidad. Es indispensable la comprobación física al colocar y retirar carga. El software tampoco puede saber si el operador hizo tara con la plataforma realmente vacía.

Cada línea es JSON. Los eventos de comandos usan `type:event`; las muestras usan `type:telemetry`, `simulated`, `uptime_ms`, `status`, `raw_mean` y `measurement`. `uptime_ms` es tiempo desde arranque, **no fecha UTC**. `raw_mean` es diagnóstico, nunca gramos.

Dentro de `measurement`, los campos del contrato comunicado son:

```json
{"schema_version":1,"device_id":"esp32-identificador","boot_id":"identificador-por-arranque","seq":1,"weight_g":250.0,"stable":true,"calibration_version":"cal-identificador-por-arranque-1"}
```

`measurement` es `null` cuando no hay peso válido. `seq` aumenta con cada medición publicada; los reintentos HTTP conservan el mismo mensaje y secuencia. El identificador de versión incluye arranque y revisión para no mezclar calibraciones entre sesiones. Las secuencias de diagnóstico no son evidencia de conexión Wi-Fi: este firmware usa **USB/serie → PC → HTTP**.

## Puente de laptop al backend

Cerrar el monitor serial antes de usar el puente: solo una aplicación puede abrir el puerto. La apertura USB puede reiniciar el ESP32. Mantener la plataforma vacía para solicitar tara explícita con `--tare-on-open`; si la ventana todavía no está lista, repetir la tara desde el monitor y comprobar el comportamiento de reinicio del puerto.

```bash
python -m pip install -r firmware/tools/requirements.txt
# Solo visualizar JSON; no envía datos a ningún servidor
python firmware/tools/serial_bridge.py --port COM3 --tare-on-open
# Enviar datos REALES al backend local ya iniciado
python firmware/tools/serial_bridge.py --port COM3 --tare-on-open --url http://127.0.0.1:8000/api/iot/measurements
# Solo entorno de pruebas: permitir datos SIMULADOS de forma explícita
python firmware/tools/serial_bridge.py --port COM3 --tare-on-open --allow-simulated --url http://127.0.0.1:8000/api/iot/measurements
```

Sin `--url` no hay tráfico HTTP. Sin `--allow-simulated` se bloquea el envío de simulaciones. Evitar esa opción contra datos de producción. El puente imprime `observed_at_utc` para auditoría de recepción en PC; ese campo queda fuera del POST. No es el instante exacto de adquisición ni sustituye `receivedAt` del servidor. El contrato espera HTTP 200 con `received:true`, `duplicate` booleano y `receivedAt` no vacío.

Reintentos: solo red, respuesta truncada o HTTP 5xx; máximo tres intentos con timeout de 2 s. HTTP 4xx, redirecciones y ACK incompatibles no se reintentan. Los reintentos conservan exactamente cuerpo, boot_id y seq. Tras enviar o descartar una muestra se vacía la cola serial para evitar reenviar lecturas acumuladas durante los reintentos. No existe cola persistente ni recuperación de mediciones perdidas. Si se interrumpe el puente, el backend/UI deben caducar la lectura (vigencia de 10 s según contrato comunicado).

## Pruebas reproducibles

Desde la raíz del repositorio, con g++ y Python 3.12:

```bash
g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/test_scale_core.cpp -o /tmp/test_scale_core
/tmp/test_scale_core
python -m pip install -r backend/requirements.txt httpx==0.28.1
python -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v
```

En Windows compilar el ejecutable C++ con g++ disponible en PATH y elegir un nombre local como `test_scale_core.exe`. Las pruebas Python no requieren pyserial; solo la ejecución del puente físico lo requiere.

El workflow `Pesaje ESP32 y pruebas de software` ejecuta esos ensayos y compila las modalidades simulada y real con Arduino ESP32 3.3.2 y HX711 0.7.5. La compilación no implica carga ni prueba física de la placa. Consultar el resultado efectivo del workflow antes de atribuirle éxito.

## Referencias técnicas

- HX711 API 0.7.5: https://github.com/bogde/HX711/blob/0.7.5/src/HX711.h
- Persistencia Preferences de Espressif: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/preferences.html
- Instalación Arduino ESP32: https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html

## Pendientes para cierre

Soldar y verificar conexiones, corregir fijación mecánica, cargar modo real, obtener respuesta repetible con carga y descarga, determinar calibración real, verificar error/repetibilidad/posición y probar contra el backend del equipo. Incorporar fotos y planilla a AGROP-21/23. No marcar estas tareas finalizadas solo por pruebas simuladas o compilación.
