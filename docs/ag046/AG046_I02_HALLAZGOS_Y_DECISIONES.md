# AG-046 / I02 — Riesgos y decisiones pendientes

**Corte:** 16/11/2026. **Sin ejecución validada aún.** Los estados de este documento se actualizan solo con evidencia de la batería local.

| ID | Control | Hallazgo de código | Estado inicial | Requisito para cierre |
|---|---|---|---|---|
| H01 | SEC-11 | `POST /api/iot/measurements` carece de autenticación de dispositivo; se esperan HTTP 200 y escritura con solicitud anónima válida en entorno aislado | **Riesgo estático; falta ejecución** | Definir si la API se expone en LAN, Internet o loopback, e introducir mecanismo de confianza o aislar el endpoint |
| H03 | SEC-12 | `/vision/quality/reviews` requiere operador, `/review-decisions` requiere revisor | **Diferencia funcional; no bug certificado** | Aprobación explícita del contrato de quién declara etiquetas experimentales y quién decide formalmente |
| H04 | MNT-01 | `backend/README.md` continúa desactualizado | Confirmado en I01; se resolverá I05 | Actualizar README según código y pruebas |

## Lectura de resultados

- La etiqueta de un test exitoso `test_sec11_...` significa que se *observó* el riesgo, no que se superó el requisito de evitar escrituras no autorizadas.
- Si `SEC-07` falla, registrar código HTTP, expediente sintético y prueba antes de alterar código.
- No unificar flujos de anotación y decisión sin especificación funcional.
- La autenticación JWT de usuarios no garantiza autenticación de una estación IoT.

## Contención temporal a revisar en I05

Hasta resolver H01, no exponer el backend sin controles de red o autenticación de dispositivo. La configuración CORS no sustituye autenticación; las solicitudes HTTP directas no dependen de CORS. Si se habilita un despliegue público, la evaluación de H01 pasa a prioritaria. No modificar firmware, API o configuraciones reales solo a partir de esta observación; primero definir contrato compatible con el puente serie.
