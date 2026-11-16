# AG-046 / AGROP-54 — I05: cierre técnico con evidencia conciliada

**Corte UTC:** 2026-11-16T15:39:48.470460+00:00
**Estado:** `CIERRE_TECNICO_AUTOMATIZADO_CON_PENDIENTES`
**Git HEAD observado al consolidar:** `42316b947fd4ce71e80b3832e70bd299ccd99d25` · rama `feature/AGROSCAN-demo-vercel`

## Evidencia de ejecución

| Incremento | Estado conciliado | Casos / controles | Ejecución seleccionada |
|---|---|---:|---|
| I01 | Checklist estático incorporado | 34 controles definidos | `AG046_I01_MATRIZ_CONTROLES.csv` |
| I02 | VALIDADO | 87 pruebas (14+24+18+18+9+4) | `AG046_I02_20261116T132352_050856Z` |
| I03 | VALIDADO | 61 pruebas (16+2+8+1+9+24+1) | `AG046_I03_20261116T141329_104177Z` |
| I04 | VALIDADO | 4/4 controles, 3 procesos secuenciales | `AG046_I04_20261116T144223_566776Z` |

## Correcciones verificadas y alcance

- **BKP-05 (I03):** inicialmente se admitió un `POST /api/lots` durante la suspensión (brecha). La corrección con guard HTTP fue reejecutada y verificada mediante la prueba estricta: **un solo proceso FastAPI**. No se acredita exclusión entre workers.
- **I02:** se corrigieron un token de prueba no ASCII, fixtures históricos sin evidencia y el recuento de Node.js. Son ajustes de pruebas/ejecutor, no cambios de autenticación.
- **I03:** se cerraron conexiones SQLite temporales en Windows para evitar `WinError 32` durante la limpieza.
- **I04:** se corrigieron la validación del sandbox y la inyección de `Request` del endpoint temporal de apagado; las pruebas de reinicio posteriores pasaron.
- **MNT-01:** README actualizado: VERIFICADO.

## Condiciones de cierre / riesgos conservados

1. **SEC-11, riesgo alto condicionado a exposición:** mediciones IoT aceptadas sin credencial. Mantener red aislada / loopback hasta definir autenticación del puente y ensayarla; CORS no protege HTTP directo.
2. **SEC-12, pendiente de negocio:** aprobar distinción entre operador (anotación experimental) y revisor (decisión formal).
3. **SEC-04:** comprobación estructural del JWT en memoria aprobada; prueba funcional en navegador pendiente.
4. **BKP-05:** no ensayado en múltiples workers o instancias, ni frente a escrituras externas y lecturas concurrentes durante restauración.
5. **INT-08:** los SHA-256 existentes validan snapshots concretos, no imágenes antiguas sin hash de captura acreditado.
6. **RST:** tres procesos Uvicorn sucesivos con SQLite temporal y fotografías sintéticas; no equivale a despliegue Render/Vercel ni a falla a mitad de transacción.

## Límites y siguiente decisión

El estado es **cierre técnico automatizado de alcance acotado**, no certificación de seguridad productiva ni cierre incondicional de AGROP-54. Publicación Git, aprobación del equipo y transición Jira quedan pendientes de acción explícita.
Revisar `AG046_I05_MATRIZ_FINAL.csv`, `AG046_I05_REGISTRO_DEFECTOS.csv` y `AG046_I05_MANIFIESTO_SHA256.csv` antes de adjuntar evidencia.

## Observaciones de evidencia (no equivalen a logs de arranque)

- I04: uvicorn_proceso_1.log está vacío (warning sin access_log); no acredita por sí mismo el arranque, usar JSON y matriz RST
- I04: uvicorn_proceso_2.log está vacío (warning sin access_log); no acredita por sí mismo el arranque, usar JSON y matriz RST
- I04: uvicorn_proceso_3.log está vacío (warning sin access_log); no acredita por sí mismo el arranque, usar JSON y matriz RST
- I04 se sustenta en JSON de resultados, checkpoints, PID únicos, comparaciones API/SQLite/SHA-256 y matriz de controles RST. Un archivo Uvicorn de 0 bytes no demuestra actividad del proceso.
