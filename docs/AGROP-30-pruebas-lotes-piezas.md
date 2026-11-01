# AGROP-30 / AG-022 — Lotes y registro de piezas

**Alcance:** abrir un lote e identificar una pieza dentro de él. Esta entrega no implementa pesaje, imágenes, clasificación ni cambios en las migraciones de AGROP-29.

## Qué ya existía en `main` (commit base `45c9607`)

- `POST /api/lots`, `GET /api/lots` y `GET /api/lots/{id}` crean y consultan lotes; el identificador de lote es único y se rechazan referencias duplicadas.
- `POST /api/evaluations` exige un lote existente y abierto; registra o reutiliza la identidad de una `Piece` dentro del lote y genera un identificador de evaluación `E-...`.
- El producto de la evaluación se toma del lote, de modo que no se mezcla mango/tomate por un campo suministrado por el cliente.
- `LotsPage` selecciona lotes abiertos; `EvaluationPage` filtra los lotes por producto y registra la pieza mediante FastAPI.
- El esquema de AGROP-29 restringe la combinación `(lot_id, code)` para piezas.

## Ajuste acotado de AGROP-30

- El frontend ahora comprueba que la respuesta de `POST /api/lots` coincida en **código, producto y estado abierto** con la petición enviada. Una respuesta distinta genera `ApiDataError`, en vez de presentar como confirmado un lote incorrecto.
- Se añaden pruebas automatizadas específicas del registro de lotes/piezas y datos identificados con prefijo `DEMO-`.

## Pruebas y evidencias

Ejecutar desde la **raíz del repositorio**, en CMD o PowerShell:

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_agrop30_lots_pieces.py" -v
cd ..\frontend
npm test
npm run lint
npm run build
```

Casos cubiertos por `test_agrop30_lots_pieces.py`:

| ID | Caso | Resultado esperado |
| --- | --- | --- |
| AG30-01 | Crear y consultar un lote demo | HTTP 201 y consultas HTTP 200, con ID y estado `open` |
| AG30-02 | Código de lote duplicado, incluso cambiando mayúsculas | HTTP 409, sin duplicar |
| AG30-03 | Producto o referencia inválidos | HTTP 422, sin guardar |
| AG30-04 | Registrar pieza para lote inexistente | HTTP 404, sin crear pieza ni evaluación |
| AG30-05 | Registrar pieza en lote cerrado | HTTP 409, sin crear pieza |
| AG30-06 | Registrar pieza en lote abierto | HTTP 201, `pieceId`, `lotId`, ID único de evaluación |
| AG30-07 | Segunda evaluación de la misma pieza | Nueva evaluación, misma entidad `Piece` del lote |
| AG30-08 | Mango y tomate en lotes distintos | Producto heredado del lote; identidades separadas |
| AG30-09 | Create/Read/Update/Delete de datos demo por ORM | Altas, consulta, modificación y borrado en SQLite **en memoria** |
| AG30-10 | Unicidad de `(lot_id, code)` | La base de datos rechaza una segunda pieza duplicada |

La prueba adicional de frontend está en `frontend/tests/api.test.mjs`: rechaza una confirmación HTTP con lote, producto o estado diferente a lo solicitado.

**Aislamiento:** los tests de backend sobrescriben la dependencia `get_db` mediante FastAPI `dependency_overrides` y usan SQLite temporal en memoria. **No modifican `backend/data/agroscan.db`** ni requieren datos, sensores o cámara reales. Cada prueba crea datos `DEMO-` y descarta su base al terminar.

**Límite explícito de CRUD:** las rutas HTTP actuales permiten creación y lectura de lotes; la edición y eliminación del ejercicio AG30-09 se ejecutan en el **ORM aislado**, no son botones ni endpoints disponibles al operador. Si la rúbrica exige **CRUD completo vía API o interfaz**, todavía faltaría definir ese alcance con el docente/equipo antes de implementar cambios destructivos que podrían afectar la trazabilidad.

**Evidencia sugerida para Jira:** salida de la suite `test_agrop30_lots_pieces.py`, resultado `npm test`, captura de la creación/selección de un lote y registro de pieza en el entorno local si se dispone de una base **de demostración**, y enlace al PR AGROP-30. No atribuir estas pruebas a la comunicación ESP32 o a pesaje calibrado.
