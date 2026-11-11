# AG-043 / AGROP-51 - Evidencia de validaciÃ³n automatizada

- Fecha de ejecuciÃ³n (local): 2026-11-11 17:54:03
- Rama: feature/AGROP-42-comparacion-metodos
- HEAD: 46c1e8f
- Resultado: **APROBADOS LOS CONTROLES AUTOMATIZADOS**
- Alcance: FastAPI (SQLite temporal e imÃ¡genes/pesos controlados), pruebas de frontend, compilaciÃ³n y revisiÃ³n Git.

| Control | Estado | Salida | Archivo de evidencia |
|---|---|---:|---|
| Backend AGROP-51 E2E mango/tomate | APROBADO | 0 | 01_backend_agrop51_e2e.txt |
| Backend adquisicion AGROP-45 (regresiones) | APROBADO | 0 | 02_backend_agrop45_regresion.txt |
| Frontend pruebas | APROBADO | 0 | 03_frontend_tests.txt |
| Frontend build TypeScript y Vite | APROBADO | 0 | 04_frontend_build.txt |
| Git diff check | APROBADO | 0 | 05_git_diff_check.txt |

## LÃ­mites de acreditaciÃ³n

- Las pruebas HTTP AGROP-51 usan FastAPI real y datos aislados/controlados: NO demuestran funcionamiento fÃ­sico de ESP32 ni captura de cÃ¡mara.
- Las pruebas frontend actuales y la compilaciÃ³n NO sustituyen una prueba funcional de interfaz en navegador, que permanece PENDIENTE de ejecuciÃ³n documentada.
- La prueba backend AG-038 (	est_agrop46_cierre_auditoria) no estÃ¡ incluida en esta ejecuciÃ³n debido al bloqueo de permisos para crear directorios temporales fuera del repositorio observado el 11/11/2026. No se declara aprobada.
- Este comando NO hace commit, push, merge, git stash pop ni modifica archivos de producciÃ³n.

## PrÃ³ximas evidencias

1. Capturas reales de navegaciÃ³n del frontend conectado a FastAPI, registrando fecha, usuario de prueba y rutas verificadas (sin secretos).
2. Registrar el estado de la prueba AG-038 en un entorno con permisos para su carpeta temporal.
3. La validaciÃ³n con hardware fÃ­sico permanece pendiente hasta disponer de cÃ¡mara y ESP32 y registrar resultados de campo.
