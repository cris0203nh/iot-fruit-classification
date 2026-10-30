# Evidencia de pruebas de software de pesaje

Ejecución local: **29 de octubre de 2026, aproximadamente 20:15, Lima** (30/10/2026 01:15 UTC). Responsable del aporte: Fernando Ramirez. Tareas: AGROP-21 y AGROP-23.

## Resultados ejecutados

| Suite | Entorno | Resultado |
| --- | --- | --- |
| Núcleo C++ compartido con el sketch | g++ 13.3.0, C++11, advertencias como errores y UndefinedBehaviorSanitizer | 16 grupos aprobados |
| Puente y contrato HTTP | Python 3.12, unittest, receptor HTTP local de pruebas | 13 casos aprobados |
| Sintaxis Python | py_compile | Aprobada |

Comandos y salida relevante:

```text
g++ -std=c++11 -Wall -Wextra -Werror -pedantic -fsanitize=undefined tests/test_scale_core.cpp -o /tmp/agroscan-scale-core-test
/tmp/agroscan-scale-core-test
16 grupos de pruebas ScaleCore aprobados

python -W error::ResourceWarning -m unittest discover -s tests -p 'test_serial_bridge.py' -v
Ran 13 tests in 3.040s
OK
```

## Cobertura comprobada

Núcleo: inicio sin sensor, falta de calibración, rechazo de tara sin ventana estable, calibración con polaridad positiva y negativa, masa inválida, exigencia de cero tras restaurar configuración, llenado de ventana, banda de cero, fuera de rango, inestabilidad, timeout, recuperación, saturación ADC, configuración inválida, desbordamiento del reloj y discontinuidad entre muestras.

Puente: selección de telemetría, ausencia de medición sin inventar cero, bloqueo de simulación por defecto, tipos y campos del mensaje, pesos no finitos o fuera de rango, estabilidad coherente, URL explícita, ACK válido, reintento de 503 y respuesta truncada con cuerpo idéntico, ausencia de reintento ante 422 o ACK inválido y límite de tres intentos.

## Compilación del sketch

Se configura compilación de las dos modalidades para NodeMCU-32S en `.github/workflows/pesaje.yml`, usando Arduino ESP32 3.3.2 y HX711 0.7.5. Consultar el resultado real del workflow en el PR; este registro local no atribuye éxito a una ejecución de CI aún no terminada.

No se pudo preparar localmente la plataforma Arduino porque la descarga de índices desde Arduino CLI no tuvo acceso de red. Esto no afecta a los resultados anteriores, que ejecutan el núcleo C++ y las pruebas HTTP localmente.

## Límites y pendientes

Las pruebas utilizan entradas sintéticas y un receptor HTTP de ensayo. No acreditan lectura de la celda, calibración física, precisión, persistencia real en NVS, comunicación USB de este nuevo sketch, desconexión física, backend del equipo ni interfaz del operador. La fixture de 100 cuentas/g no es un factor real.

Continuar con montaje firme y soldado, carga del sketch en la placa y ensayos con masas conocidas. Registrar error, repetibilidad y posición en la planilla de AGROP-23. Mantener AGROP-21 y AGROP-23 pendientes de validación física.

## Traslado al repositorio grupal del 30 de octubre de 2026

Repositorio de trabajo del equipo: `cris0203nh/iot-fruit-classification`. Se trasladan firmware, puente, simulador anterior, pruebas y documentación desde el repositorio de Fernando, sin reemplazar backend, frontend ni sus documentos.

Después del traslado se ejecutaron **16 grupos C++ y 23 pruebas Python aprobadas**. Las 23 pruebas incluyen 13 del puente, 5 del simulador y 5 de integración con las rutas IoT reales del backend del equipo. Se instalaron las dependencias de `backend/requirements.txt` y httpx 0.28.1 en un entorno aislado. Comando: `python -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v`.

La integración usa una API de ensayo con el router `backend/app/routers/iot.py` y SQLite en memoria: recepción de payload del firmware, duplicado sin refrescar receivedAt, simulador aceptado en entorno aislado, rechazo 422 de datos inválidos, caducidad de lecturas y estado inestable. No usa la base de datos del equipo ni datos reales. No valida todavía el recorrido completo de evaluaciones, USB físico ni persistencia NVS.

Se ajustó el límite de identificadores del puente a 64 caracteres para coincidir con el esquema real del backend. El simulador anterior incorpora también reintento ante respuestas HTTP incompletas. El código fuente de backend y frontend permanece intacto.

Procedencia de los cambios: [PR 2 original](https://github.com/Fernando270-11/iot-fruit-classification/pull/2), commits originales `649aecbee595162691e0eff129638674612e5ac9`, `ea907629e660958c262337c06dd60b3538e59b60` y `fdc29822298ec72fa515ca9d1e572f1424a206f5`; [simulador original PR 1](https://github.com/Fernando270-11/iot-fruit-classification/pull/1). Los commits del traslado mantienen los identificadores AGROP-21 y AGROP-23 y registran esta procedencia.

Para reproducir la integración: instalar `backend/requirements.txt` y `httpx==0.28.1`, luego ejecutar las pruebas desde la raíz. El workflow del repositorio grupal vuelve a ejecutar pruebas y compilaciones; consultar su resultado efectivo antes de atribuir éxito.
