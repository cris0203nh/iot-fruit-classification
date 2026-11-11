# AgroScan — AG-037 / AGROP-45: bloqueo de resultados dudosos

Historia Jira: «Como revisor, quiero identificar resultados dudosos para no aceptarlos automáticamente».
Dependencias: AG-035 y AG-036 (desarrolladas previamente; no se reimplementan aquí).

## Implementación (primer bloque)

Se integra un control *posterior a la adquisición*, sobre fotografías **guardadas**; no se bloquea una captura por cada fotograma de la cámara en vivo.

1. `POST /api/evaluations/{id}/vision/review-gate` recibe `{"imageId":"I-000001"}` y ejecuta YOLOE con `imgsz=512`, `conf=0.25`, `iou=.50`, sin modificar pesos ni prompts. La regla de aceptación sigue en 0,40. Si faltan detecciones, clase de fruta, segmentación, confianza suficiente o si existen múltiples candidatos, se registra `pending_review`. Si el detector falla, también queda pendiente; jamás se acepta por omisión. Si es apta, **solo se acepta la detección**, nunca se emite E0/E1/E2.
2. Cada inferencia, incluida la apta, se almacena como un **snapshot independiente** en `vision_assessments`: fotografía, SHA256, versión declarada del modelo/reglas, tamaño, confianza, cajas, clases, máscara y resultado. El archivo, `visual_category` inicial y revisiones anteriores se preservan. La tabla tiene restricción única por foto/hash/reglas/modelo; no hay endpoint de modificación o eliminación.
3. La página de evaluación invoca el control **después** de confirmar peso+fotografía con FastAPI, cuando todas las vistas ya están guardadas. La interfaz indica «Pendiente» o «Detección apta; calidad sin determinar». Si falla la comunicación, informa el problema y ofrece reintentar, sin fingir un dictamen.
4. El rol revisor/admin, desde **Trazabilidad → Detalle**, puede marcar una foto como dudosa con justificación; se agrega `Review(type='uncertainty')`, sin modificar el snapshot previo. El operador no puede marcar objeciones manuales.
5. `POST /api/evaluations/{id}/vision/resolve` exige rol revisor/admin y `status=pending_review`. Permite `E0`, `E1`, `E2` o `no_evaluable` con justificación; crea un **evento humano** independiente, cierra la cola (`status=completed`) sin escribir sobre `Evaluation.visual_category`. El dictamen final manual puede consultarse en la trazabilidad; `no_evaluable` no inventa un grado E0/E1/E2.
6. `GET /api/evaluations/{id}/vision/assessments` permite auditar el snapshot original y la salida del detector. El historial ya permite filtrar por `pending_review`; la trazabilidad presenta registros automáticos y eventos humanos separados.

## Matriz de criterios

| Criterio | Cómo se verifica |
|---|---|
| Resultado incierto queda pendiente | API devuelve `pending_review`, SQLite persiste evento `uncertainty`, no hay categoría automática |
| Conservar entrada original | Foto original y SHA256 permanecen iguales; snapshots solo se agregan, no se reescriben |
| No-evaluable y revisión | Se muestra opción `no_evaluable`, se guarda decisión con autor/motivo y la imagen no cambia |
| Umbral sustentado | Informe AG-036/Incremento 06: 97 imágenes, reglas 0,40/0,30/0,25 y 32 casos rechazados revisados. **Es justificación exploratoria, no calibración estadística concluyente**. |

## Umbral experimental existente (sin extrapolar a E0/E1/E2)

| Umbral captura | Imágenes aptas en ensayo retrospectivo 97 |
|---:|---:|
| 0,40 | 65 |
| 0,30 | 83 |
| 0,25 | 86 |

El detector procesó 97 fotos, pero solo se verificaron manualmente los 32 rechazos. Los 65 admitidos inicialmente carecen de verificación humana equivalente; no se conoce la tasa de aceptación errónea en el universo. Por ello **no se modifica el umbral 0,40** en este incremento. La incertidumbre de clasificación de calidad E0/E1/E2 requerirá otro umbral y otro modelo, todavía no acreditados.

## Instalación Windows (raíz del repo)

**Antes de migrar, respalde `backend/data/agroscan.db`.** El cambio de esquema es aditivo; conserva registros históricos.

```powershell
# 1. sincronizar rama después de los PR anteriores
 git switch feature/AGROP-42-comparacion-metodos
 git fetch origin --prune
 git merge --ff-only origin/main

# 2. comprobar y aplicar parche
$patch = "$env:USERPROFILE\Downloads\AG037_Implementacion_Integral.patch"
git apply --unidiff-zero --check "$patch"
if ($LASTEXITCODE -ne 0) { throw "Parche no aplicable" }
git apply --unidiff-zero "$patch"
if ($LASTEXITCODE -ne 0) { throw "Fallo al aplicar el parche" }
git diff --check

# 3. respaldo de SQLite
$database = ".\backend\data\agroscan.db"
if (Test-Path $database) {
  Copy-Item $database "$database.pre_AG037_$(Get-Date -Format yyyyMMdd_HHmmss).bak"
}

# 4. migrar base de datos (detener backend antes de hacerlo)
Push-Location backend
& ".\.venv\Scripts\python.exe" -m alembic upgrade head
Pop-Location

# 5. pruebas backend y frontend
Push-Location backend
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -p "test_agrop45_uncertainty.py" -q
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -p "test_*.py" -q
Pop-Location
npm --prefix frontend test
npm --prefix frontend run build
```

**No haga `git add .`:** podrían incluirse datasets o evidencias privadas. Incluya únicamente los archivos de AG-037 del parche (ver guía).

## Comprobación manual

1. Con un usuario operador, realice una evaluación y almacene fotos. Tras confirmación de adquisición, React ejecuta la verificación en las imágenes persistidas.
2. Ante una detección no confiable, compruebe `pending_review` en Historial y que la fotografía sigue disponible en Trazabilidad.
3. Inicie sesión como revisor y, desde Trazabilidad → Detalle, consulte la salida del detector, el SHA y el motivo. Seleccione `no_evaluable` o, solo si hay evidencia humana real, E0/E1/E2; escriba la justificación y registre.
4. Confirme que aparece el evento de resolución, estado `completed`, y el snapshot de detección y archivo original siguen disponibles.
5. Un operador no debe poder resolver un pendiente. Intentar un valor distinto de E0/E1/E2/no_evaluable debe devolver HTTP 422.

## Limitaciones reales

- El conjunto de 97 imágenes es evidencia de *detección*, no de clasificación E0/E1/E2. Este bloque no entrena un clasificador ni supone que E0/E1/E2 están automáticamente disponibles.
- `completed` tras `no_evaluable` significa **resolución del proceso de revisión**, no que exista una clasificación de calidad válida. La decisión final está en el evento humano; el valor original no se sobrescribe.
- El identificador de modelo de los snapshots es declarativo local, no una certificación criptográfica de los pesos; para auditoría externa debe documentarse SHA256 de pesos/prompts por separado.
- La verificación automática se ejecuta tras la confirmación de adquisición que requiere dos pesajes: si el hardware no está disponible, se puede probar la ruta manual sobre registros e imágenes existentes, y probar el backend con simuladores sin afirmar pruebas físicas.
- La evaluación en vivo `/vision/detect` sigue sin persistir cada frame. La revisión se activa en una imagen guardada, evitando congestionar SQLite.
- Este es el **bloque de implementación integral**; el informe experimental de cierre de AG-037 y la validación prospectiva de umbrales pertenecen al bloque 2.
