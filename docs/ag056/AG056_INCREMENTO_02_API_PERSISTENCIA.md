# AG-056 — Incremento 02: API y persistencia

**Alcance:** adaptador de lectura SQLite + API de cola; la bandeja React corresponde al Incremento 03. El endpoint no infiere modelos, no modifica la evaluación, no confirma E0/E1/E2 y no sobrescribe fotografías.

## Arquitectura

- `backend/app/review_queue.py` lee por lotes `evaluations`, `lots`, `images`, `reviews`, `review_decision_evidence`, `vision_assessments`, `ag055_quality_predictions` desde la base SQLite existente.
- Contrasta hash SHA-256 de la fotografía física antes de considerar una decisión humana válida. Rutas inexistentes, fuera del directorio de datos, enlaces simbólicos, tamaño erróneo o contenido distinto no equivalen a un cierre. Si existe una señal para esa foto, el motor eleva el caso.
- Convierte las filas existentes a `EvaluationFacts` y ejecuta `select_for_human_review` del Incremento 01, sin modificar su contrato.
- Evita consultas N+1 mediante consultas por lote de 100 evaluaciones y un prefiltro SQL de estados/señales. El conteo total y ordenamiento requieren recorrer las candidatas filtradas antes de paginar; esto es preciso pero implica I/O de fotografías por solicitud, por lo que para producción de gran volumen deberá medirse y evolucionarse el rendimiento sin saltar pendientes.
- No se crea tabla ni migración Alembic: las decisiones permanecen en AG-038; guardar una segunda cola con estados podría introducir inconsistencias.
- Las solicitudes concurrentes son lecturas del estado en ese momento. Las mutaciones deben seguir pasando por los endpoints AG-038 con control de revisiones. El endpoint no reserva ni bloquea trabajos.

## API

`GET /api/reviews/queue` requiere token de rol **revisor** o **administrador**. `operador` recibe HTTP 403; sin autenticación, HTTP 401.

Parámetros: `lot` (código de lote, sin distinguir mayúsculas), `product=mango|tomate`, `priority=high|normal`, `limit` (1..100; defecto 20) y `offset` (0 o mayor; defecto 0).

Ejemplo de respuesta (valores ilustrativos, no datos reales):

```json
{
  "items": [{
    "evaluationId": "E-000001", "lotId": "LOTE-01", "pieceId": "PIEZA-01",
    "product": "mango", "status": "pending_review", "registeredAt": "2026-11-13T15:00:00+00:00",
    "imageCount": 2, "imageIds": ["I-000001"], "priority": "high",
    "reasons": [{"code": "uncertain_detection", "priority": "high", "imageId": "I-000001", "source": "ag037-assessment:1"}],
    "ruleVersion": "ag056-review-selection-v1"
  }],
  "total": 1, "limit": 20, "offset": 0, "hasMore": false,
  "counts": {"high": 1, "normal": 0, "all": 1},
  "ruleVersion": "ag056-review-selection-v1"
}
```

Orden estable: casos `high` primero, luego `normal`; dentro de cada grupo, fecha de creación ascendente y `evaluationId` ascendente. `total` refleja el filtro de `priority`; `counts` refleja las candidatas revisables filtradas por lote y producto **antes** de filtrar prioridad.

## Límites y pendientes

1. No modificar el estado `completed` cuando una vista sigue pendiente: el motor la mantendrá en la cola si persisten señales sin decisión aplicable. Las rutas antiguas que marcan `completed` prematuramente requieren una revisión coordinada antes del cierre funcional de AG-056; esta API no altera su semántica de escritura.
2. No utilizar la cola como prueba de aprobación de modelos AG-055: todos sus resultados E0/E1/E2 siguen siendo experimentales. La confianza de YOLOE valida detección, no calidad de fruta.
3. Las anotaciones AG-055 almacenadas fuera de SQLite no sustituyen las decisiones humanas canónicas AG-038.
4. Si el volumen crece, medir I/O y latencia; no introducir cachés de SHA que permitan cerrar con evidencia alterada.
5. Incremento 03: vista `/revisiones`, navegación según rol, paginación y enlaces a detalle/decisión.

## Pruebas

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_ag056_*.py" -v
```

Se espera ejecutar las 35 pruebas de I01 más las pruebas de integración de I02 en el ambiente del proyecto. El ZIP y parche no se deben confundir con un despliegue o una validación contra datos operativos reales.

## Commit selectivo (después de ejecutar y revisar los tests)

```powershell
git add backend/app/review_selection.py backend/app/review_queue.py backend/app/routers/review_queue.py backend/app/main.py backend/tests/test_ag056_review_selection.py backend/tests/test_ag056_review_queue.py docs/ag056/
git diff --cached --check
git diff --cached --stat
```

Este `git add` explícito evita que se versionen por accidente los archivos de AG-034/AG-036, datasets u otros archivos sin seguimiento detectados en el directorio de trabajo del usuario.
