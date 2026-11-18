# Etapa 05 — Detección de cambios, integración y gate global

**Referencia:** `main` tras el PR #87, commit `6ceb7e5ee12bc0e4c8ceedd33f6db89b73d06c04`.

## Diseño de ejecución

`Preparación → Detectar cambios → Backend/Frontend/IoT/Visión (según rutas) → Integración (cuando aplica) → CI final`.

- `Seguridad` (Bandit, auditorías Python/npm, Gitleaks y contratos) se ejecuta **siempre** y es obligatoria.
- `DAST` se ejecuta ante cambios de API/backend/visión o cambios globales. No usa infraestructura ni datos reales.
- `workflow_dispatch` ejecuta todos los módulos. Una base SHA ausente, inaccesible o divergente también activa **todos** los módulos.
- Se mantienen `pull_request` hacia `main` y `push` a `main` con un solo workflow coordinador y reutilizables (`workflow_call`).
- Cambios de documentación omiten módulos computacionalmente costosos pero **no** seguridad. Cambios en CI, seguridad, rutas desconocidas y archivos raíz no documentales requieren ejecución completa.
- Un cambio en `backend/app` activa backend, visión e IoT, integración y DAST por los contratos compartidos. Cambios en firmware activan IoT e integración. Cambios de frontend TS/TSX activan frontend e integración; cambios CSS o imágenes solo frontend.
- La selección no puede convertir un fallo o un `cancelled` en `skipped` permitido: `check_gate.py` exige `success` para todo job seleccionado; para los deseleccionados exige exactamente `skipped`.

## Integración reproducible

`integracion.yml` verifica, con temporales y sin hardware físico:

1. Flujo HTTP de pesaje, capturas y revisión humana simulado (`test_agrop45_flujo_integral_simulado.py`).
2. Contratos HTTP E2E de mango y tomate (`test_agrop51_e2e_mango_tomate.py`).
3. Piloto A/B multiempresa, roles y puente IoT HTTP autenticado (`test_saas08_pilot.py`).
4. Restricciones del proxy local de demostración (`test_agroscan_demo_deploy.py`).

Estos tests **no certifican** la precisión E0/E1/E2 ni la conexión física ESP32/cámara/báscula.

## Cierre esperado del PR

1. Validar `python -m unittest discover -s scripts/ci -p 'test_*.py' -v` y sintaxis YAML; verificar `git diff --check`.
2. Verificar mediante PR real el grafo completo (primera ejecución: cambios `.github/workflows` activan todos).
3. Ejecutar en un PR de prueba seguro de solo documentación: backend/frontend/IoT/visión/DAST/integración deben quedar `skipped`; **Seguridad y CI global deben aprobar**.
4. Para un fallo controlado en una rama de prueba, confirmar que un job requerido fallido o un estado ambiguo bloqueen la validación global. No fusionar ese cambio deliberadamente fallido.
5. No ocultar hallazgos de seguridad. La excepción documentada de `picomatch` en Etapa 04 sigue con vencimiento 01/12/2026 UTC; esta etapa no la modifica.

## Límites

La selección por rutas es conservadora, no un analizador estático perfecto de dependencias. Cambios no reconocidos ejecutan todo. Las omisiones justificadas solo certifican que el diff no seleccionó ese módulo, no que se haya ejecutado su suite. No hay despliegue automático ni manejo de credenciales reales.
