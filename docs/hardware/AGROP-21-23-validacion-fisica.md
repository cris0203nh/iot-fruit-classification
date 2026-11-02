# AGROP-21 y AGROP-23 Avances físicos de Fernando

Actualización documental del 01/11/2026. Fuente: fotografías, lecturas y confirmaciones de Fernando, recogidas en los informes Word de AGROP-21 y AGROP-23 adjuntos en Jira. Este registro complementa las pruebas de software anteriores; no acredita una ejecución física del firmware versionado.

## Montaje comprobado

- ESP32 NodeMCU-32S, HX711 y celda actual rotulada **10 kg**, que sustituye a la celda inicial de 5 kg.
- DT en GPIO32 y SCK en GPIO33; pruebas de monitor serie en COM3, 115200 baudios.
- Montaje recibido soldado; Fernando confirmó conexiones visualmente correctas, sin contactos accidentales, platos sin contacto y fijaciones firmes con zona de flexión libre.
- Continuidad y tensión **no medidas** por falta de multímetro. No registrar aprobación instrumental.
- La capacidad rotulada no certifica el rango del conjunto. El contrato de la API sigue limitado a 0–5000 g.

## Lecturas y ensayos físicos

Las fotografías muestran un sketch de diagnóstico con lectura cruda, peso, amplitud y estabilidad. Se registró factor de trabajo **145,18 cuentas/g** y offset de una tara **−313147 cuentas**. El offset corresponde a esa sesión; no debe copiarse como calibración universal. No se ha identificado el commit exacto de ese sketch ni acreditado su equivalencia con firmware/agroscan_scale.

Referencias de ensayo: frasco indicado como 229 g y botella indicada como **385 g** en balanza SF-400. Son referencias comparativas; no se aporta certificado metrológico.

| Ciclo | Botella g | Vacío posterior g |
| --- | ---: | ---: |
| 1 | 386,2* | +1,1 |
| 2 | 385,9 | +1,0 |
| 3 | 384,6 | −0,5 |
| 4 | 385,1 | +0,8 |
| 5 | 386,4 | +0,4 |

*El informe fuente interpreta el primer mensaje como 386,2 g y conserva una observación de confirmación pendiente. Los resúmenes que usan ese valor son provisionales: media 385,64 g, diferencia frente a referencia +0,64 g y amplitud 1,8 g. No se resta retrospectivamente el vacío posterior.

| Posición | Lectura g |
| --- | ---: |
| Centro | 386 |
| Delante | 409 |
| Detrás | 368 |
| Izquierda | 411 |
| Derecha | 404 |

La amplitud de 43 g entre posiciones revela sensibilidad importante a la colocación. Se acordó uso centrado para el prototipo; no se acredita exactitud en toda la plataforma ni se elimina la limitación mecánica.

| Minutos sin carga | Lectura g |
| --- | ---: |
| 0 | 0,4 |
| 5 | 1,2 |
| 10 | 1,6 |
| 20 | 1,3 |
| 30 | 1,7 |

Cambio observado +1,3 g en 30 minutos. El episodio previo comunicado de deriva de aproximadamente 0 a 10 g no se reprodujo en esta serie, pero no queda descartado. Tras otra tara, las últimas lecturas fotografiadas se aproximan a cero. Las fechas y condiciones exactas de cada ensayo no se registraron individualmente.

## Estado documental y evidencia

- [AGROP-21](https://feramirez055.atlassian.net/browse/AGROP-21): montaje e inspección visual documentados, tarea finalizada.
- [AGROP-23](https://feramirez055.atlassian.net/browse/AGROP-23): informe de calibración y verificación adjunto. Consultar Jira para el estado actual; este registro no lo modifica.
- Informe de montaje: Sprint_04_AGROP21_Montaje_Pesaje_IoT.docx, versión interna 1.0.
- Informe de verificación: Sprint_04_AGROP23_Calibracion_Verificacion_Pesaje.docx, versión interna 1.0.

Las fotografías originales permanecen en los informes de Jira. No se han vuelto a cargar aquí ni se presentan como pruebas de transporte HTTP.

## Integración todavía por comprobar

La lectura física por serie no demuestra recepción en AgroScan. Para AGROP-22 y AGROP-31 falta registrar una ejecución con:

1. Identidad del sketch cargado, modo real y calibración de la sesión.
2. Telemetría JSON compatible con el puente. Una línea de diagnóstico como “Peso: 385 g” no es su contrato.
3. Puente USB/serie a HTTP ejecutado con --url y ACK del backend.
4. Peso real vigente visible en la interfaz y caducidad al detener la publicación.
5. Registro del peso en la evaluación correcta para AGROP-31.

La ruta implementada por el firmware revisado es ESP32 → USB/serie → PC → HTTP. No incorpora envío Wi-Fi directo. El firmware del repositorio inicia en simulación por defecto; compilar con AGROSCAN_SIMULATION=0 para HX711 real. No se ha comprobado qué versión está instalada actualmente en la placa de Fernando.
