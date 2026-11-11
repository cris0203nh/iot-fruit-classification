# AgroScan — AG-040 / AGROP-48 — Incremento 02: reporte exportable y cierre técnico

## Alcance y prerrequisito

El Incremento 01 se fusionó mediante PR #69 el 9/11/2026, commit `63c4670730ac2d42c84341de30dbe0eb8162b92e`. Este incremento añade el informe exportable, pero no crea capturas ni acredita inspección física.

**API:** `GET /api/piece-history/report?lot=CODIGO` exige JWT de administrador, operador o revisor y devuelve un JSON con `rows`, `counts`, `integrity`, `csv`, `csvSha256`, `generatedAt` y `reportVersion` (`AG040-02-v1`). Las respuestas usan `Cache-Control: no-store`. El JSON no contiene bytes de fotografías ni tokens de sesión.

**Frontend:** En Historial integral, consultar lote, pulsar **Preparar reporte de lote**, inspeccionar auditoría y exportar CSV o manifiesto JSON. El CSV se deshabilita ante estado `inconsistent`; siempre queda disponible el JSON para diagnóstico. Un reporte exportado corresponde a una fotografía lógica de la BD al consultar, no a una certificación permanente del estado actual.

## Semántica de los conteos

| Indicador | Unidad contada | Identidad |
| --- | --- | --- |
| `pieceCount` | Una pieza por lote | `(lot_id, piece.code)` o código histórico inferido |
| `attemptCount` | Un intento | `evaluations.id` |
| `captureCount` | Una foto persistida | `images.id` |
| `automaticAssessmentCount` | Una evaluación automática registrada | `vision_assessments.id` (puede haber varias por foto) |
| `reviewEventCount` | Un evento de revisión | `reviews.id` |

El reporte tiene **exactamente una fila por pieza**, incluso cuando no tiene intentos. Incluye las listas vinculadas de identificadores (`E-`, `I-`, snapshots, `R-`) y versiones, sin multiplicar piezas por JOIN. Un código histórico sin FK se incluye con advertencia, nunca como evidencia de identidad física acreditada.

La auditoría recalcula los totales desde las tablas originales y contrasta cada fila con el resumen del Incremento 01. Señala: referencias de foto ajenas en snapshots o decisiones, SHA256 contradictorios, fotografía sin SHA256 referenciado, identidad histórica inferida y divergencia de conteos. FKs de pieza contradictorias siguen produciendo HTTP 409 (Incremento 01). La ausencia de SHA256 no se rellena ni estima.

El SHA256 del CSV corresponde **solo a los bytes UTF-8 exactos de su contenido**, incluidos los saltos de línea CRLF; no verifica la existencia física ni integridad binaria actual de las imágenes. El CSV protege frente a inyección de fórmulas al abrirlo en hojas de cálculo.

## Pruebas de aceptación

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_agrop48_piece_history.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
cd ..\frontend
npm test
npm run build
```

Casos: tres intentos sobre una sola pieza, pieza sin intentos, pieza histórica, 2 snapshots sobre la misma fotografía, reconciliación de conteos, SHA divergente, evidencia referenciada fuera del expediente, 401 sin JWT, exportaciones repetidas con mismo hash CSV, códigos potencialmente peligrosos para Excel y bloqueo de CSV ante inconsistencia.

## Evidencias para Jira AGROP-48

1. URL de PR/commit de Incremento 02 y verificación CI (adjuntar una vez ejecutados).
2. Captura de Historial con lote de prueba y el panel del reporte (pieza, intentos, fotos, snapshots y revisiones).
3. CSV y manifiesto JSON descargados desde un entorno con datos reales de pruebas **identificados como tales**, más sus SHA256 y fecha.
4. Capturas de consola de las pruebas de backend/frontend y `npm run build`.
5. Confirmar en Jira que AG-039 está aceptado, si es dependencia del cierre administrativo.

**Criterio de cierre:** contar con pruebas ejecutadas en el entorno de integración, evidencia descargable auténtica y PR de este incremento fusionado. La existencia del parche por sí sola **no** acredita esas condiciones ni permite declarar AGROP-48 cerrado.
