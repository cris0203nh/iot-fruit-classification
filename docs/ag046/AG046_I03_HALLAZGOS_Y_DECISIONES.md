# AG-046 / I03 — Hallazgos y decisiones de integridad

**Situación inicial:** evidencia de revisión estática; pendiente de ejecutar la batería en el checkout local.

| Referencia | Control | Observación inicial | Estado de auditoría | Acción de cierre |
|---|---|---|---|---|
| H02 | BKP-05 | `suspend_capture()` bloquea operaciones que usan `capture_guard`; `POST /api/lots` no declara esa dependencia en `main` auditado | **Brecha potencial — prueba estricta preparada** | Ejecutar `test_ag046_i03_bkp05.py`, guardar HTTP obtenido, evaluar corrección de los endpoints de escritura y pruebas de concurrencia |
| INT-C01 | INT-08 | Los snapshots y decisiones contienen SHA-256, pero `Image` no almacena un hash original universal de captura | **Limitación de cobertura del registro histórico** | No acreditar integridad criptográfica de imágenes sin hash histórico; valorar seguimiento como mejora |
| RST-01…RST-04 | Reinicio | I03 no detiene ni arranca el proceso FastAPI | **No probado en I03** | Desarrollar I04 con BD descartable y una instancia real del servidor |

## Regla de hallazgos

- Si BKP-05 arroja **HTTP 201** durante suspensión: registrar como **defecto reproducido** y no aprobar BKP-05. El nombre `BRECHA_BKP05_CONFIRMADA` no implica que la solución esté implementada.
- Si BKP-05 arroja **HTTP 503** y la prueba estricta pasa: registrar alcance limitado (una ruta y un proceso); todavía no atribuir seguridad general al despliegue.
- Si otra prueba falla: registrar traza, escenario sintético, fecha, commit y severidad; no cambiar los criterios para acomodar el resultado.
- Los riesgos SEC-11 y SEC-12 siguen abiertos desde I02. No se modifican sus estados en I03.

**Acción propuesta para I05:** cubrir de forma coherente las escrituras protegidas durante backup/restauración, incluyendo registros de lotes, evaluaciones, decisiones y mediciones, sin introducir bloqueos que afecten el puente IoT. Antes de corregir se debe confirmar la política de despliegue y el modelo de concurrencia (un proceso frente a varios).
