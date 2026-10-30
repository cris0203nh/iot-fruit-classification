# AGROP-22 · [AG-014] Visualización del peso y su estado

## Estado y alcance

Integración **solo de lectura** del frontend con `GET /api/iot/status` de FastAPI, usando la estructura existente. No crea ni guarda pesos en una evaluación, no confirma que el ESP32 haya sido programado con el nuevo firmware y no acredita calibración física.

El ZIP auditado contiene backend FastAPI/SQLite y frontend React; **no incorpora** `firmware/agroscan_scale/agroscan_scale.ino` ni el puente serial/HTTP documentados por Fernando en su PR 2. Por tanto, el adaptador debe incorporarse o validarse por el equipo, sin inventar un endpoint alternativo.

## Contrato utilizado

```
GET /api/iot/status
{
  "online": true,
  "deviceId": "station-001",
  "weightG": 250,
  "stable": true,
  "receivedAt": "2026-10-29T23:00:00+00:00",
  "ageSeconds": 0.8
}
```

- `receivedAt` es la fecha de **recepción en FastAPI**, no un reloj certificado del ESP32.
- El backend considera vigentes las lecturas por un máximo de 10 segundos.
- El frontend también vence localmente la lectura si no llega una respuesta nueva dentro de ese intervalo.
- Si `online=false` o se pierde la conexión HTTP, el peso visible desaparece; el historial no se borra.
- Si `stable=false`, la masa se muestra con advertencia, pero no es registrable.
- El contrato actual **no indica si la lectura es real o simulada**: no se debe presentar como medición física comprobada.

## Prueba de software

Desde `frontend`: `npm test`, `npm run lint`, `npm run build`.

Desde `backend`: `python -m unittest discover -s tests -p 'test_*.py' -v`.

Para probar vía API de manera controlada, iniciar FastAPI y enviar una muestra **de ejemplo** con `/docs` o `curl`:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/iot/measurements -ContentType application/json -Body '{"schema_version":1,"device_id":"station-demo","boot_id":"demo-01","seq":1,"weight_g":250,"stable":true,"calibration_version":"sin-calibracion-fisica"}'
```

Consultar `/api/iot/status` y la página **Evaluación** en React. Variar `seq` y `stable` para comprobar la vista inestable; detener las publicaciones y esperar 10 s para comprobar caducidad. La desconexión HTTP debe mostrar error sin reutilizar peso.

Para la prueba específica **ESP32 → PC**, usar la simulación y el puente desarrollados por Fernando (cuando estén disponibles en la máquina), **sin inventar una ejecución física**. Adjuntar serial y respuesta HTTP reales; registrar ID de firmware/commit, fecha, modo simulado/real y resultados observados.

## Evidencia de Jira para cierre

- Captura con peso y fecha real de recepción en UI, estado **estable** e identificación del dispositivo.
- Captura con la muestra `stable=false`, sin habilitar registro.
- Captura de lectura vencida o sensor desconectado, sin peso vigente.
- Registro serial ESP32–PC o video (expresamente solicitado en Jira) y prueba end-to-end con su modo de origen identificado.
- PR/commit vinculado a `AGROP-22`; validación del equipo de que el puente entrega el JSON acordado.

**AGROP-22 queda pendiente de la evidencia serial ESP32–PC y la integración física si no se ejecutan.** La visualización puede probarse con la API usando muestras de ensayo.
