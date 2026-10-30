# iot-fruit-classification
MVP de clasificación IoT de mango y tomate

## Pesaje IoT del Sprint 4

El firmware ESP32/HX711 está en [`firmware/agroscan_scale`](firmware/agroscan_scale). Incluye simulación explícita, tara, calibración y estados de lectura. El puente USB/serie a HTTP está en [`firmware/tools`](firmware/tools).

- [Guía de conexión y ejecución](docs/AGROP-21-AGROP-23-pesaje.md)
- [Simulador Python sin hardware](docs/AGROP-21-simulador-pesaje.md)
- [Pruebas y alcance de validación](docs/AGROP-21-AGROP-23-pruebas.md)

Las pruebas de software y compilación no sustituyen la validación física ni la calibración con masas conocidas.
