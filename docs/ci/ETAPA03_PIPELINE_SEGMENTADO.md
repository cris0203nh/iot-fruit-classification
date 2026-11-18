# Etapa 03 — Pipeline CI segmentado y coordinado

Base: `main` posterior al PR #85 (compilación ESP32 y pruebas de pesaje corregidas).
Esta etapa organiza CI, **no despliega**, no modifica aplicación, modelos, SQLite, hardware ni credenciales reales.

## Arquitectura

Un único workflow activador `.github/workflows/ci.yml` ejecuta:

1. `preparacion`: verifica los archivos/versiones base de los cuatro componentes.
2. Cuatro workflows reutilizables en paralelo con `needs: preparacion`:
   - `backend.yml`: pruebas de `backend/tests` y controles del proxy de demostración.
   - `frontend.yml`: `npm ci`, ESLint, pruebas JS/TS y build Vite.
   - `pesaje.yml`: integración de IoT SaaS-07, puente serial, simulador, ScaleCore C++ y dos compilaciones ESP32.
   - `vision.yml`: `vision/tests` y regresiones geométricas I03 de `tests/`.
3. `ci` (`if: always()`): publica resumen en GitHub Actions y **falla** si alguna dependencia está `failure`, `skipped` o `cancelled`.

Los cuatro workflows de módulos se activan solo desde el coordinador (`workflow_call`), por lo que no duplican eventos de push/PR. El coordinador se activa en PR hacia `main`, push a `main` y manualmente desde Actions. Las ramas de trabajo se validan por su PR; no se ejecuta otra vez al hacer cada push de la rama.

## Dependencias de pruebas y aislamiento

- Python 3.12; Node 22; ejecución Linux `ubuntu-24.04`.
- Backend/visión: `backend/requirements.txt`, `opencv-contrib-python-headless==4.12.0.88` y `Pillow==12.3.0`. No se instala Ultralytics/CLIP ni se hace inferencia/training físico; las pruebas de contratos aplicables usan dobles de prueba.
- IoT: solo requisitos de FastAPI y pruebas de pesaje, sin instalar OpenCV innecesariamente.
- Cada runner Python crea un `AGROSCAN_DATA_DIR` temporal y una clave JWT generada para la ejecución; no se utiliza `backend/data`, `.env` ni secretos humanos. Los tests pueden crear otras bases temporales.
- Los tests no prueban exactitud E0/E1/E2 con fotos reales ni aceptación de hardware físico.

## Aceptación de la Etapa 03

- PR: cuatro componentes aprobados, `ci` verde, sin desactivar pruebas para forzar éxito.
- Confirmar visualmente el grafo `Preparación -> [Backend, Frontend, IoT, Visión] -> CI`.
- Verificar que IoT sigue compilando firmware real/simulado y que los tests separados no duplican las mismas pruebas.
- Validar que un error real de un módulo provoca `ci` rojo antes de fusionar.
- Mantener el PR abierto hasta comprobar los resultados de GitHub Actions; ejecución local o validación YAML no equivale a ejecución CI.

## Fuera de alcance de Etapa 03

- Etapa 04: incorporar controles DevSecOps (SAST, SCA, secretos, DAST).
- Etapa 05: detectar archivos modificados y aplicar jobs condicionales; pruebas de integración entre etapas.
- Etapa 06: políticas de checks obligatorios y reportes ampliados.

## Operación

`ci.yml` es el punto único de activación. No lanzar `pesaje.yml`, `backend.yml`, `frontend.yml` o `vision.yml` individualmente desde Actions: estos son componentes reutilizables. Si hay fallos, abrir el job exacto y revisar el traceback. No fusionar el PR antes de tener `CI - validación global` aprobado.
