# AGROP-21: preparación de la comunicación de peso

Contribución del módulo IoT de Fernando Ramirez: cliente Python para simular
lecturas y ejercitar el contrato de recepción comunicado por el equipo.
Es un avance de integración; no completa el montaje AGROP-21 ni la calibración AGROP-23.

## Ejecución local

Requiere Python 3.10 o posterior, sin paquetes adicionales. Desde la raíz del repositorio:

```bash
python firmware/weight_simulator.py --weights 0 152.8 480 0 --stable
python -m unittest discover -s tests -p "test_weight_simulator.py" -v
```

Sin `--url`, imprime JSON y no se conecta a ningún servidor. `--stable` representa
un estado simulado; sin esa opción usa false. No implementa el algoritmo de estabilidad.
Cada ejecución genera un UUID para boot_id; seq crece por medición.
Usa device_id `simulator-fernando-001` y calibration_version
`simulated-not-calibrated` para distinguir estos datos del hardware real.

## Integración con el backend del equipo

Solo cuando esté disponible, usar un entorno de pruebas:

```bash
python firmware/weight_simulator.py --weights 152.8 --stable --url http://127.0.0.1:8000/api/iot/measurements
```

127.0.0.1 se refiere a la computadora que ejecuta este script. Para otro equipo,
usar su dirección accesible. Este comando escribe mediciones simuladas: no apuntarlo
a un entorno con datos reales. El backend del equipo está en `backend/` y su contrato en `docs/api-contract.md`; ejecutar únicamente sobre una instancia local de pruebas.

El contrato comunicado exige schema_version, device_id, boot_id, seq, weight_g,
stable y calibration_version. Acepta 0–5000 g y responde HTTP 200 con received,
duplicate y receivedAt. Este cliente valida pesos finitos y comprueba esa respuesta.
En red/5xx reintenta hasta tres veces con el mismo JSON y clave de idempotencia;
en 4xx no reintenta. No sigue redirecciones ni mantiene una cola de envíos antiguos.
El receptor debe resolver duplicados y antigüedad/orden de lecturas.

## Verificación realizada

Pruebas automatizadas con servidor HTTP local de prueba:
- Recepción válida y duplicado sin una segunda identidad almacenada.
- Respuesta 503 tras recepción: reenvío idéntico y reconocimiento de duplicado.
- HTTP 422 sin reintento.
- HTTP 503 persistente: finaliza después de tres intentos.
- Límites 0/5000 aceptados; negativos, sobrecarga, NaN e infinito rechazados.

Estas pruebas verifican el cliente contra un servidor de prueba, no el backend de
la compañera. No prueban ESP32, HX711, calibración, vigencia de GET /api/iot/status
ni despliegue. Pendiente acordar la integración con la responsable backend.

## Evidencias para S10

1. Descargar esta rama en la computadora del estudiante y ejecutar los comandos.
2. Capturar la consola con el JSON, aviso SIMULACIÓN y resultado de las pruebas.
3. Capturar el commit y el PR en GitHub, con archivos modificados visibles.
4. Para el requisito de despliegue, ejecutar la integración contra el servidor de
   pruebas acordado y capturar su respuesta. Un PR o el JSON sin envío no acredita despliegue.

Informe personal: describir el cliente de pruebas, validaciones, identidad de
mediciones y reintentos; adjuntar capturas auténticas de cada entorno. No afirmar
montaje físico, calibración o despliegue que no se hayan realizado.
