# AG-046 — Registro inicial de hallazgos y defectos

**Corte:** 2026-11-16. **Naturaleza:** auditoría estática. Este archivo **no afirma ejecución de pruebas**. Un hallazgo de alcance o una brecha de evidencia no es automáticamente una vulnerabilidad reproducida.

| Identificador | Severidad preliminar | Tipo | Estado al cierre I01 | Próxima acción |
|---|---|---|---|---|
| AG046-H01 | Alta **si API pública** | Riesgo de superficie IoT | Por validar | Probar y definir mecanismo de confianza del dispositivo |
| AG046-H02 | Alta | Riesgo de concurrencia en restauración | Por reproducir | Ensayo aislado con escrituras simultáneas |
| AG046-H03 | Media | Diferencia de permisos en flujos humanos | Requiere decisión funcional | Establecer permisos esperados antes de corregir |
| AG046-H04 | Baja | Error de documentación | Confirmado por inspección | Actualizar README y verificar con código |
| AG046-H05 | Media | Falta de evidencia integral de reinicio | Abierto como brecha de prueba | Ejecutar y documentar I04 |
| AG046-H06 | Media | Cobertura heterogénea de hashes | Por evaluar | Delimitar qué endpoints deben verificar byte/hash |

## Fichas

### AG046-H01 — Ingesta IoT
- **Referencia:** `backend/app/routers/iot.py`, `POST /api/iot/measurements` y `GET /api/iot/status`.
- **Observado:** no usan `Depends(get_current_user)` ni otra credencial visible en esa ruta.
- **Impacto potencial:** lectura no autorizada o contaminación de mediciones si el servicio fuese accesible fuera de una red de confianza.
- **Pendiente:** definir el despliegue real y las garantías del enlace USB/HTTP; no etiquetar como explotación confirmada.

### AG046-H02 — Exclusión durante restauración
- **Referencia:** `backend/app/services/capture_control.py`, `backend/app/routers/backup.py`, `backend/app/routers/evaluations.py`, `backend/app/routers/iot.py`.
- **Observado:** el mecanismo de suspensión requiere que la operación utilice `capture_guard`; varias escrituras no lo incluyen.
- **Impacto potencial:** inconsistencias o pérdida de escrituras concurrentes durante el reemplazo de SQLite/archivos.
- **Pendiente:** prueba de concurrencia y revisión de transacciones activas en ambiente efímero; no ejecutarla sobre DB personal.

### AG046-H03 — Diferencia de privilegios de revisiones
- **Referencia:** `backend/app/routers/quality_prediction.py` (`/vision/quality/reviews`) usa `require_operator`; `backend/app/routers/review_decisions.py` usa `require_reviewer`.
- **Observado:** ambos endpoints registran acciones de naturaleza distinta; no se ha acreditado que compartan la misma política de permisos.
- **Pendiente:** acordar si una declaración de anotación experimental puede hacerla un operador; probar el contrato aceptado, no asumir defecto.

### AG046-H04 — README desactualizado
- **Referencia:** `backend/README.md`, sección «Limitaciones actuales».
- **Observado:** afirma «Sin migraciones», «Sin inicio de sesión» y respaldo pendiente; existen migraciones Alembic, autenticación y respaldo en `main`.
- **Pendiente:** actualizar instrucciones de arranque, JWT, Alembic, acceso API, respaldos y advertencia de no borrar SQLite real.
- **Reproducción:** comparar texto del README con los archivos versionados. No requiere ejecutar código.

### AG046-H05 — Reinicio integral no acreditado
- **Referencia:** `backend/tests/test_agrop52_recovery.py`, `backend/tests/test_agrop52_image_recovery.py` y suite AGROP-53.
- **Observado:** existen pruebas de fallos, reintentos y restauración, pero en esta revisión no se dispone de una ejecución que detenga e inicie un proceso FastAPI y valide todas las entidades de un expediente completo.
- **Pendiente:** protocolo I04 y captura de IDs, estados, hashes y registros antes y después.

### AG046-H06 — Política de integridad de imágenes
- **Referencia:** `backend/app/routers/images.py` y `backend/app/routers/review_decisions.py`.
- **Observado:** `GET /api/images/{id}` comprueba existencia; rutas específicas calculan SHA. Es necesario especificar el nivel de verificación exigido para servir originales y restaurarlos.
- **Pendiente:** prueba de archivo ausente/alterado y reglas de aceptación del proyecto.

## Plantilla para nuevos bugs reproducidos

```text
ID: AG046-BUG-XX
Asociación: AG046-HXX / control XXX
Entorno + SHA:
Severidad:
Estado: NUEVO | REPRODUCIDO | EN_CORRECCION | CORREGIDO | VERIFICADO | ACEPTADO_CON_RIESGO
Precondiciones (solo datos sintéticos):
Pasos exactos:
Esperado:
Obtenido:
Evidencia (log/captura sin secretos):
Cambio/PR:
Regresión que prueba corrección:
Responsable y fecha:
```

**Regla de cierre:** no marcar un bug como `VERIFICADO` por leer una corrección. Reproducir, cambiar, repetir caso adverso y guardar log en el mismo corte.
