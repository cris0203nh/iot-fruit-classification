# Pesaje IoT con ESP32 y HX711

Firmware de AGROP-21 y comandos de tara/calibración de AGROP-23. El sketch inicia en **simulación explícita**, sin necesitar hardware. Las pruebas de software no certifican una balanza calibrada.

- Abrir `agroscan_scale/agroscan_scale.ino` en Arduino IDE.
- Guía de conexiones, comandos, simulación y validación: [`../docs/AGROP-21-AGROP-23-pesaje.md`](../docs/AGROP-21-AGROP-23-pesaje.md).
- Puente USB/serial al backend: `tools/serial_bridge.py` (Python 3.12 y pyserial 3.5).
- Núcleo compartido y probado en C++: `agroscan_scale/ScaleCore.h`.
- CI: `../.github/workflows/pesaje.yml` compila las dos modalidades para NodeMCU-32S.

También se incorpora `weight_simulator.py`, el cliente Python anterior, con su guía y pruebas. El firmware ESP32 no depende de él. Ver `../docs/AGROP-21-simulador-pesaje.md`.
