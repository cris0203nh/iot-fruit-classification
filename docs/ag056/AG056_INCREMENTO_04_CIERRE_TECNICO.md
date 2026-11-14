# AG-056 — Incremento 04 · Pruebas finales y cierre técnico

**Estado del desarrollo:** corrección implementada y verificada mediante pruebas aisladas. **Cierre de aceptación local y PR:** pendientes de que el responsable aplique el parche y ejecute la batería en su repositorio. Este documento no afirma haber usado sensores, imágenes reales ni base productiva.

## 1. Problema identificado y solución

AG-038 registraba una decisión sobre una foto y cambiaba inmediatamente `Evaluation.status` a `completed`, incluso cuando otra vista requería revisión. El Incremento 04 elimina esa transición automática:

- `backend/app/review_completion.py` verifica fotografías físicas y el número de imágenes, consulta decisiones AG-038 asociadas a imagen y SHA-256, y reutiliza **el mismo motor AG-056** que construye la bandeja. Una decisión no acredita las otras fotos ni propuestas de IA posteriores.
- **Dos vistas en una evaluación `pending_review` requieren cobertura humana de ambas**, aun cuando todavía no existe modelo AG-055. Se preserva la compatibilidad de las resoluciones históricas AG-037 con una sola fotografía.
- `POST /api/evaluations/{id}/review-decisions` realiza `flush` de Review y ReviewDecisionEvidence *antes* de reconciliar el estado; conserva bloqueo `BEGIN IMMEDIATE`, `requestId`, `expectedReviewId`, el log append-only y el valor inicial inmutable. La transacción se confirma una sola vez.
- La evidencia de AG-055 exige que los SHA-256 de sus fuentes coincidan antes de permitir una nueva decisión humana sobre esa fotografía. Si la procedencia está corrupta o incompleta, devuelve 409.
- La ruta genérica antigua `/reviews` recibe 409 y revierte la escritura si aún existen fotos/incidencias pendientes. La resolución antigua `/vision/resolve` no puede cerrar simultáneamente varias imágenes inciertas ni otras incidencias de calidad; en esos casos exige decisiones AG-038 por imagen.
- React selecciona la siguiente fotografía sin revisar; para casos de identidad concreta restringe el selector a las IDs indicadas por AG-056. Reutiliza el mismo panel AG-038 sin crear otro registro de decisiones.

El estado `completed` aquí solo significa **sin trabajo pendiente según las señales y evidencias disponibles**. No valida E0/E1/E2 experimental ni el desempeño del clasificador. Las incidencias sin procedencia verificada requieren recuperación manual; **no deben forzarse a `completed`**.

## 2. Matriz de aceptación

| Caso | Resultado requerido |
|---|---|
| Dos fotos con propuesta E0/E1/E2: revisar primera | HTTP 201; `pending_review`; segunda continúa en cola |
| Revisar segunda foto | HTTP 201; `completed`; cola vacía para ese expediente |
| Dos fotos sin modelo de calidad: revisar primera | Mantener `pending_review` hasta revisar la segunda |
| Nueva instantánea experimental después de revisar | Reabre el caso; decisiones anteriores no la resuelven |
| Archivo inexistente, tamaño incorrecto o SHA distinto | No cerrar; decisión con fuente AG-055 alterada devuelve 409 |
| Repetición del mismo `requestId` | Respuesta idempotente; sin duplicar Review/metadata |
| Segundo revisor con `expectedReviewId` obsoleto | 409, sin decisión adicional |
| Operador intenta consultar bandeja o registrar decisión | 403 |
| Revisor y administrador consultan bandeja | 200 |
| Ruta antigua intenta ocultar señales AG-056 | 409 y rollback; bitácora intacta |
| Dos fotos AG-037 pendientes en ruta de resolución global | 409; exigir decisión individual |
| Sin servidor, sesión caducada, evidencias incompletas | Error explícito; no confundir con cola vacía |

## 3. Pruebas automatizadas

Ejecutar desde la raíz del repositorio en **Windows PowerShell**:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_ag056_*.py" -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_agrop45_uncertainty.py" -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_agrop46_review_decisions.py" -v
cd frontend
npm run build
npm test
node --experimental-strip-types --test tests/ag056-review-queue.test.mjs tests/ag056-review-queue-http.test.mjs tests/ag056-review-final.test.mjs
npx eslint src/App.tsx src/app/navigation.ts src/pages/ReviewQueuePage.tsx src/features/reviews/reviewQueuePolicy.ts src/features/reviews/pendingImagePolicy.ts src/features/traceability/ReviewDecisionPanel.tsx src/services/agroscanApi.ts
cd ..
git diff --check
```

En el entorno aislado de preparación, antes de empaquetar: **63 pruebas Python AG-056**, incluidas nueve nuevas de reconciliación SQLite, y **5 pruebas nuevas de selección frontend**: aprobadas. **Las pruebas API completas `test_ag056_final_api.py`, el build integral y la batería existente deberán ejecutarse localmente** en el repositorio completo. Las 9 pruebas de endpoints finales no se han ejecutado aquí contra su FastAPI real.

El `npm run lint` global ya reportaba **8 errores y 4 advertencias en otros módulos no relacionados** con AG-056 (captura, evaluación, geometría y administración); no ocultarlos ni atribuirlos al nuevo incremento. El lint selectivo sirve para probar únicamente los archivos afectados por AG-056.

## 4. Validación manual antes de fusionar

1. Arrancar FastAPI y Vite, iniciar sesión como **revisor**.
2. Abrir `/revisiones` con una evaluación `pending_review` de dos fotografías; si no existe, crear un expediente de prueba con las rutas normales, sin inventar evidencia.
3. Revisar la primera fotografía y comprobar que la segunda siga pendiente y el estado **no** sea `completed`.
4. Revisar la segunda, consultar `/api/reviews/queue` y `/api/evaluations/E-xxxxxx/review-decisions` y verificar que el estado cambie únicamente cuando corresponda.
5. Iniciar sesión como operador y verificar que la ruta/bandeja no le autoriza consultas ni guardados.
6. Confirmar que las fotografías siguen idénticas y que el registro original no fue reemplazado.
7. No usar este ejercicio como validación experimental de E0/E1/E2; cualquier decisión de prueba debe quedar identificada como tal.

## 5. Entrega selectiva y PR

Antes de staging, inspeccionar `git status --short`. El usuario ya informó archivos **ajenos a AG-056** sin seguimiento y modificados; no usar `git add .`, `git clean -fd` ni `git reset --hard`.

Archivos AG-056 para revisión y staging selectivo:

```text
backend/app/review_selection.py
backend/app/review_queue.py
backend/app/review_completion.py
backend/app/routers/review_queue.py
backend/app/routers/review_decisions.py
backend/app/routers/evaluations.py
backend/app/routers/uncertainty.py
backend/app/main.py
backend/tests/test_ag056_review_selection.py
backend/tests/test_ag056_review_queue.py
backend/tests/test_ag056_review_completion.py
backend/tests/test_ag056_final_api.py
frontend/src/App.tsx
frontend/src/app/navigation.ts
frontend/src/pages/HomePage.tsx
frontend/src/pages/ReviewQueuePage.tsx
frontend/src/pages/ReviewQueuePage.css
frontend/src/features/reviews/reviewQueuePolicy.ts
frontend/src/features/reviews/pendingImagePolicy.ts
frontend/src/features/traceability/ReviewDecisionPanel.tsx
frontend/src/services/agroscanApi.ts
frontend/tests/ag056-review-queue.test.mjs
frontend/tests/ag056-review-queue-http.test.mjs
frontend/tests/ag056-review-final.test.mjs
frontend/tests/ux-layout.test.mjs
docs/ag056/
```

**No incluir `frontend/package.json`**: el Incremento 03 se aplicó excluyéndolo por conflicto local. Ejecutar el test nuevo mediante el comando específico anterior. Los cambios de `backend/app/routers/evaluations.py` y `uncertainty.py` son defensas contra escrituras antiguas que podían omitir el bloqueo AG-056.

Una vez que toda la batería indicada pase, y tras comprobar que `git diff --cached --stat` solo incluye los archivos deseados, crear commit, publicar la rama `feature/AG-056-cola-revision-humana` y abrir PR hacia `main`. El merge y Jira no están hechos por este kit.

### Estado recomendado para Jira

> AG-056: Incrementos 01–03 validados localmente; Incremento 04 implementa reconciliación de decisiones por fotografía, integridad SHA-256, prevención de cierre prematuro y compatibilidad controlada con rutas antiguas. Pruebas aisladas de selección y SQLite aprobadas; validación integral de FastAPI, React, flujo humano en navegador y revisión de PR pendientes antes del cierre definitivo. La clasificación E0/E1/E2 conserva carácter experimental.
