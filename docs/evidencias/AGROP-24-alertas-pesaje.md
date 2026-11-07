# AGROP-24 - Validacion funcional de alertas de pesaje

## Objetivo
Verificar el tratamiento de errores de pesaje antes de confirmar una evaluacion.

## Resultados de integracion con hardware real
- Dispositivo: ESP32 + HX711.
- Modo: simulated=false.
- Estado sin cero confirmado: zero_required.
- Medicion sin cero confirmado: measurement=null.
- Despues de establecer el cero: stable=true.
- Confirmacion de cero: zero_confirmed=true.

## Validacion del software
Se aprovecha la funcionalidad de control de errores
implementada previamente en AgroScan.

Se conserva el tratamiento de lecturas invalidas
antes de confirmar una evaluacion.

## Conclusion
Se verifico la comunicacion con hardware real y el
reconocimiento del estado de ausencia de cero.

Los resultados se registran sin repetir pruebas
fisicas ya realizadas ni modificar funcionalidades existentes.
