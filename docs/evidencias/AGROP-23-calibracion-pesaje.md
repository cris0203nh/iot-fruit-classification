# AGROP-23 - Calibracion y verificacion de pesaje

## Pruebas realizadas
- Hardware: ESP32 + HX711 + celda de carga de 5 kg.
- Modo: hardware real (simulated=false).
- Masa utilizada para calibracion: mango de 250 g.
- Masa de verificacion: tomate de 100 g.

## Parametros reportados por STATUS
- Offset: -215833.4000
- Counts per gram: 129.20520000
- Revision: 6

## Resultados de pesaje del tomate

| Posicion | Referencia | Promedio medido |
|---|---:|---:|
| Centro | 100 g | 107.020 g |
| Derecha | 100 g | 115.755 g |
| Izquierda | 100 g | 180.348 g |

## Observaciones
- Se obtuvieron cinco lecturas consecutivas por posicion en las dos ultimas mediciones.
- Las lecturas reportaron estado stable=true.
- Se identificaron desviaciones entre posiciones.
- No se declara exactitud satisfactoria.
- Los parametros de STATUS se registran tal como fueron reportados por el dispositivo.
- Se requiere revisar la desviacion detectada antes de considerar validada la exactitud.

## Resultado
Pruebas fisicas de calibracion y pesaje realizadas.
Desviaciones detectadas y registradas para seguimiento.
