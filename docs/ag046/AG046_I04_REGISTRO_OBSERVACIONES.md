# AG-046 / I04 — Registro de observaciones para cierre

**Estado al crear el incremento:** pruebas preparadas sin ejecución local confirmada.

| Registro | Clasificación | Descripción | Estado |
|---|---|---|---|
| I04-OBS-01 | Límite de validez | Un proceso/worker por vez; no prueba bloqueo de escrituras entre distintas instancias FastAPI. | Fuera de alcance I04; revisar en I05 si la demo despliega varios procesos. |
| I04-OBS-02 | Límite de validez | Parada forzada luego de una respuesta 2xx; no comprueba recuperación de escritura interrumpida antes del commit. | Fuera de alcance I04. |
| I04-OBS-03 | Evidencia adicional | Validación operativa y captura en navegador no son sustituidas por pruebas con datos temporales. | Pendiente si se exige por el curso/Jira. |
| I04-OBS-04 | Dependencia documental | Los controles SEC-11, SEC-12 y SEC-04 del I02 continúan limitados según su propia evidencia. | Conservar para I05. |

**Instrucción de registro:** una falla real debe documentarse con paso, error, archivo de log y fecha; no completar el estado como corregido sin una nueva ejecución aprobada.
