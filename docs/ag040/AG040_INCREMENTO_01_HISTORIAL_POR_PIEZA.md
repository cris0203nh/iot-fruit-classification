# AgroScan — AG-040 / AGROP-48 — Incremento 01: historial integral por pieza y lote

## Propósito

Jira: «Como revisor, quiero revisar el historial completo de una pieza por lote». Criterios: capturas, intentos, modelo y regla versionados, revisiones, y sin duplicar piezas. Este incremento implementa **consulta de expediente y navegación React**; el reporte exportable auditado y sus evidencias de cierre corresponden al Incremento 02.

Se reutilizan `lots`, `pieces`, `evaluations`, `images`, `vision_assessments`, `reviews` y `review_decision_evidence`; **no se crea una tabla nueva ni se requiere migración**. La dependencia AG-038 ya está desarrollada; AG-039 requiere revisión de su implementación/aceptación en Jira antes del cierre administrativo.

## Contrato de lectura

- `GET /api/piece-history?lot=<CODIGO>`: un elemento por código de pieza dentro del lote, incluyendo piezas registradas sin intentos, evaluaciones históricas sin FK y contadores de intentos, fotos, detecciones automáticas y eventos de revisión.
- `GET /api/piece-history/<LOTE>/<PIEZA>`: expediente con todos los intentos `E-...`, fechas, estados, datos de pesaje registrados, fotografías `I-...`, snapshots YOLOE con `modelVersion`/`rulesVersion` y decisiones `R-...`, incluyendo la acción y el hash SHA256 cuando el metadato existe.
- Ambos endpoints exigen JWT válido por `require_authenticated`. Son GET de **solo lectura**; los archivos originales siguen protegidos por el endpoint de imágenes ya existente.
- React presenta el expediente en el **Historial** mediante un selector de lote, una fila por pieza y un desplegable por intento. Las fotos usan `ProtectedEvidenceImage` con autorización, no tokens en URL.

## Reglas de integridad

1. La identidad operativa se considera `(lot_id, piece.code)`, no `evaluation.id` ni `image.id`. Las evaluaciones se agrupan por `(lot_id, piece_id)`; las FK normalizadas deben concordar con el código. Si contradicen el código, el endpoint falla con HTTP 409 **sin mezclar registros**.
2. La base `pieces` tiene un índice único de `(lot_id, code)`. Una evaluación histórica sin `piece_ref_id` se asocia por código al lote; cuando no existe `Piece` se muestra `legacy_inferred` y una advertencia: **no se garantiza independencia física** a partir de códigos antiguos.
3. El conteo se realiza desde evaluaciones sin unir simultáneamente fotografías, snapshots y revisiones (lo que multiplicaría filas). Los acumulados se consultan con `COUNT/GROUP BY` independiente y se suman por evaluación.
4. Se distinguen intentos persistidos de capturas descartadas antes de guardar: las segundas **no existen** en SQLite y no se inventan.
5. Las versiones del detector provienen de los snapshots guardados. Si una evaluación no tiene snapshot, se informa lista vacía y versión declarativa `null`, no se inventa un modelo. YOLOE detecta, no clasifica E0/E1/E2.
6. La imagen conserva su URL protegida y un SHA256 vinculado a los eventos/snapshots disponibles; si no existe ningún hash se indica «No registrado». Si los hashes de la misma imagen divergen se marca `hashConflict`, sin elegir uno de forma arbitraria.
7. Las revisiones heredadas de AG-037 pueden carecer de acción o SHA individual; se exponen con `null`, sin fabricarlos.

## Evidencia automatizada incluida

- `backend/tests/test_agrop48_piece_history.py`: agrupa varias evaluaciones de la misma pieza, conserva 4 fotos, 2 snapshots y 3 revisiones sin inflar piezas, verifica roles, histórico sin FK, piezas vacías, códigos repetidos en distintos lotes, conflicto de FK y no mutación.
- `frontend/tests/agrop48-piece-history.test.mjs`: verificador de coherencia del contrato de agregación (no oculta duplicados ni totales incorrectos).

Este conjunto utiliza SQLite temporal y datos de prueba controlados. No acredita experimentación con ESP32 físico ni una inspección visual del navegador. El Incremento 02 deberá adjuntar capturas auténticas de Historial y Trazabilidad con datos de pruebas e informe deduplicado.

## Comprobación (PowerShell desde raíz)

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
& $py -m unittest discover -s backend/tests -p 'test_agrop48_piece_history.py' -v
& $py -m unittest discover -s backend/tests -p 'test_*.py' -q
node --experimental-strip-types --test frontend/tests/agrop48-piece-history.test.mjs
npm --prefix frontend test
npm --prefix frontend run build
```

**Nota Windows:** si aparece `ModuleNotFoundError: app` al ejecutar pruebas desde la raíz, usar `Push-Location backend`, ejecutar la suite con `-s tests`, y luego `Pop-Location` como indica la guía del kit.

No ejecutar `git add .` porque la copia local puede contener archivos privados de datasets o incrementos anteriores. Registrar solamente archivos AG-040 del parche.
