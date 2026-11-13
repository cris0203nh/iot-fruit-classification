# AG-055 I04 — Validación funcional, incertidumbre y revisión humana

Estado: **implementado y validado técnicamente**, en `feature/AGROP-67-calidad-externa`.
Ejecución local iniciada el 12 de noviembre de 2026, America/Lima; los eventos guardan UTC.
E0/E1/E2 continúa **sin acreditación**. No se reentrenaron modelos, añadieron datasets,
ejecutaron migraciones, crearon ramas ni modificaron decisiones históricas.

## Resultado funcional y evidencia real

Chromium/Playwright ejecutó la aplicación React y FastAPI con los modelos reales I03.
Se inició sesión con un operador exclusivamente de ensayo y se seleccionó una evaluación
existente de la base aislada. Su fotografía original fue persistida con SHA-256 verificado:
`TQ_000871`, Rotten original, que el modelo predice Fresh con score 0,9031.
La interfaz la deriva a revisión prioritaria por posible Rotten, manteniendo intacta
la predicción Fresh. Esto **no corrige la etiqueta ni reduce los falsos negativos del modelo**.

El navegador comprobó inferencia real desde el botón React, scores y margen, lectura de
la fotografía autenticada, ROI, guardado y corrección de revisión, recuperación después
de recargar/iniciar sesión y reintento de inferencia con los mismos IDs, sin duplicados.
Se validaron móvil a 390×844, ausencia de desbordamiento horizontal y errores de conexión,
HTTP sin fotografía y ausencia de modelo. **Estos tres fallos de UI se inyectaron con rutas
Playwright**; las rutas exitosas, fotografía, modelo y persistencia no usan mocks.
Las comprobaciones backend también cubren ausencia real de foto/modelo y fallo de inferencia.

Artefactos privados: `%USERPROFILE%\Documents\AgroScan_AG055_I04_01`:

- `browser/result.json`: pasos y resultado del E2E.
- `browser/01-real-inference-uncertainty.png`: inferencia y derivación reales.
- `browser/02-review-event-test-only.png`, `03-correction-preserves-history.png`.
- `browser/04-mobile-review.png`, `04-mobile-viewport.png`: capturas reales de Chromium.
- `browser/05-http-no-photo-error.png`, `06-disconnection.png`, `07-no-model.png`.
- `browser/sanitized-quality-responses.json`: respuestas sin tokens/contraseñas ni rutas privadas.
- `real_photo_provenance.json`, `python_test_results.json`, `final_validation.json`.
- `data/test.sqlite`, `review_queue/`: base/cola aisladas; nunca son datos humanos acreditados.

Los eventos E2E están marcados `automated_test_not_human_ground_truth`; no verifican
ROI humana y el entrenador de revisiones los excluye. La automatización simula el formulario
para probar software, no suplanta a un revisor real. No se creó ninguna etiqueta humana real.

## Incertidumbre y límites medidos

Los umbrales se derivan **solo de validación** y se vinculan al hash del modelo y versión
de datos. No son calibración de probabilidades. Se conservan todas las puntuaciones
originales y el margen entre las dos categorías principales. La UI dice «Confianza no calibrada».

| Producto | Política congelada con validación |
|---|---|
| TQ, 396 fotos | Margen ≤0,962927 o score Rotten ≥0,022584: revisión prioritaria; Rotten predicho también prioritario |
| SEN, 166 fotos | Margen ≤0,703570 o categoría de enfermedad: revisión prioritaria |
| FGrade | Solo diagnóstico experimental; nunca autoriza decisiones operativas |

El margen se fija al percentil 95 de los márgenes de errores de validación. Para TQ se
elige el mayor umbral de score Rotten que retiene al menos 95% de los Rotten de validación.
La política combinada deriva 83/86 Rotten de validación (96,51%) y 243/396 imágenes (61,36%).
Sin política compatible o evidencia suficiente se exige revisión, sin inventar umbrales.
Toda propuesta sigue requiriendo revisión humana, incluso con prioridad normal.

Después de congelar `uncertainty_policy.json`, se evaluó prueba **sin cambiar umbrales**:

| Producto | Fotos prueba | Priorizadas | Errores originales | Errores priorizados |
|---|---:|---:|---:|---:|
| TQ | 369 | 256 | 57 | 55 |
| SEN, cinco clases originales | 169 | 140 | 40 | 38 |

TQ mantiene 48 Rotten→Fresh; **46 se derivan a prioridad y 2 no**. No existe garantía
de detección segura. La carga de revisión es alta y la independencia física de fruta/sesión
sigue sin acreditarse. Ver `uncertainty_policy_evaluation.json` para los recuentos congelados.
La inferencia SEN conserva sus categorías originales, sin acreditar Kent ni mapear a E0/E1/E2.

## Revisión, permisos e integridad

Se reutiliza `vision/ag055/review.py`: mismos eventos JSON append-only y misma cola;
`registered_samples/` añade referencias a fotos persistidas, no copias de fotografías.
El React integrado permite abrir original/ROI, ajustar ROI, elegir E0/E1/E2/no evaluable,
anotar rúbrica y justificación/evidencia, y consultar estado e historial.
E1/E2 exige criterio Rxx. El revisor proviene del usuario autenticado, no de un campo editable.

- `GET /api/evaluations/{id}/vision/quality/reviews`: usuario autenticado.
- `POST .../vision/quality/reviews`: operador/administrador, declaración explícita,
  ROI confirmada, inferencia y foto de la misma evaluación, SHA coincidente.
- Una corrección exige el último ID observado y crea un evento con `supersedesEventId`;
  una edición obsoleta devuelve 409. Se conserva la inferencia original y cada revisión anterior.
- No se escribe `visual_category`, estado de evaluación ni decisiones oficiales.
  Los eventos declaran `accreditationVerified=false` y autenticidad humana no comprobada.
- Se rechazan suplantación por campos adicionales, evidencia alterada, ROI fuera de rango,
  falta de autorización, inferencia ajena, cancelación y fallos de almacenamiento.
- La política forma parte de la identidad de inferencia: repetir con igual evidencia/política
  devuelve el snapshot existente; cambiar política genera un nuevo snapshot auditable.

No hubo cambios de esquema. El SHA de `backend/data/agroscan.db` coincide con el
respaldo verificado I03. Todas las escrituras del ensayo ocurrieron fuera de Git.

## Pruebas ejecutadas

- Backend completo: **227/227**, incluidas AG-053/054 y cuatro pruebas nuevas I04.
- Visión AG-055: **23/23**, incluidas tres pruebas de umbrales/routing/procedencia.
- Frontend completo: **111/111**, incluidos contratos de scores/revisión y render React.
- TypeScript/Vite build: correcto. ESLint de calidad y cliente API: correcto.
- E2E Chromium real: aprobado, sin excepciones JavaScript. Capturas inspeccionadas.

Logs: `backend_tests_verified.log`, `vision_ag055_tests_verified.log`, `frontend_tests.log`,
`frontend_build.log`. Los ensayos negativos AG-035 escriben un mensaje esperado de rechazo;
la suite completa termina `OK` y código 0, ver `python_test_results.json`.
El lint global conserva los problemas ajenos ya documentados en I03; no se amplió este alcance.

## Windows: ejecución de la aplicación

Desde la raíz, usar Python original para poder guardar revisiones fuera del repositorio:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend;$PWD\backend\.venv\Lib\site-packages"
$env:AGROSCAN_EXPLORATORY_MODELS_PATH = "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run02\models"
$env:AGROSCAN_UNCERTAINTY_POLICY_PATH = "$env:USERPROFILE\Documents\AgroScan_AG055_I04_01\uncertainty_policy.json"
$env:AGROSCAN_REVIEW_RUN = "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run02"
py -3.13 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Otra terminal, desde frontend: npm run dev
```

Iniciar sesión, abrir captura/trazabilidad, inferir y pulsar «Revisar I-…».
La cuenta revisor mantiene su permiso de consulta; no se amplían sus privilegios.
No usar `AGROSCAN_TEST_INSTANCE=1` ni la aplicación fixture para anotaciones reales.
No iniciar el servicio offline de revisión como sustituto de la autenticación de FastAPI.

Para volver a derivar umbrales, usar una **salida nueva**, sin entrenar modelos:

```powershell
py -3.13 -m vision.ag055.uncertainty `
  --run "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run02" `
  --output "$env:USERPROFILE\Documents\AgroScan_AG055_I04_01\uncertainty_policy_rerun01.json"
py -3.13 -m unittest discover -s backend/tests -q
py -3.13 -m unittest discover -s vision/tests -p 'test_ag055_*.py' -q
# Desde frontend: npm test; npm run build
```

Para reproducir el navegador, definir este bloque en terminales de API y prueba:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend;$PWD\backend\tests;$PWD\backend\.venv\Lib\site-packages"
$env:AG055_REAL_RUN = "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run02"
$env:AG055_I04_EVIDENCE = "$env:USERPROFILE\Documents\AgroScan_AG055_I04_01"
$env:AG055_TEST_PASSWORD = 'I04-local-fixture-only!'
# Terminal API:
py -3.13 -m uvicorn ag055_i04_app:app --host 127.0.0.1 --port 18004
# Terminal frontend (desde frontend):
$env:VITE_API_BASE_URL = 'http://127.0.0.1:18004'
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
# Terminal prueba (raíz, bloque común anterior):
$env:AG055_PLAYWRIGHT_ROOT = "$env:USERPROFILE\Documents\AgroScan_AG055_I04_tools"
$env:AG055_CHROMIUM_PATH = "$env:LOCALAPPDATA\ms-playwright\chromium-1248\chrome-win64\chrome.exe"
node frontend/tests/ag055-i04-e2e.mjs
```

Playwright se instaló únicamente en la carpeta externa de herramientas; Chromium ya estaba
disponible. No se modificaron dependencias del repositorio ni permisos del sistema.
La repetición conserva los eventos previos del ensayo y comprueba el incremento exacto de dos.

## Archivos de I04

| Archivo | Cambio |
|---|---|
| `vision/ag055/uncertainty.py` | Nuevo: derivación, carga y evaluación de políticas congeladas |
| `vision/ag055/review.py` | Reutilización de cola/eventos, correcciones y no evaluable |
| `vision/tests/test_ag055_uncertainty_i04.py` | Nuevo: contratos de incertidumbre |
| `backend/app/routers/quality_prediction.py` | Routing, revisión autenticada e integridad |
| `backend/tests/test_ag055_i04.py` | Nuevo: permisos, historial e invariantes |
| `backend/tests/ag055_i04_app.py` | Nuevo: aplicación aislada E2E, sin mocks de inferencia |
| `frontend/src/services/agroscanApi.ts` | Contratos y llamadas de revisión |
| `frontend/src/features/quality/exploratoryPolicy.ts` | Validación y textos de incertidumbre |
| `frontend/src/features/quality/ExploratoryPanel.tsx` | Scores, margen, prioridad y acceso a revisión |
| `frontend/src/features/quality/HumanReviewPanel.tsx` | Nuevo: original/ROI, anotación e historial |
| `frontend/src/features/quality/quality.css` | Nuevo: formulario y fotografías responsive |
| `frontend/tests/ag055-quality.test.mjs` | Contratos I04 y compatibilidad del render existente |
| `frontend/tests/ag055-i04-e2e.mjs` | Nuevo: navegador real y captura de evidencias |
| `docs/ag055/AG055_INCREMENTO_04.md` | Este informe |

## Pendientes exactos para I05

1. Revisión humana real competente, rúbricas aprobadas y evidencia de identidad/licencia por
   fotografía. Las referencias nuevas de evaluaciones no se promocionan a entrenamiento
   mientras su identidad/licencia estén pendientes. No hay doble revisión independiente acreditada.
2. Calibración defendible y evaluación independiente por fruta/sesión, cámara y producto;
   variedad Kent acreditada para afirmar desempeño en ese alcance.
3. Acordar capacidad de revisión y criterios de aceptación por clase: el routing actual
   prioriza 256/369 fotos TQ y todavía deja dos Rotten→Fresh fuera de prioridad.
4. Validación de estación e iluminación/cámara; ArUco no es requisito del clasificador de defectos.
5. Antes de un despliegue multiworker: coordinar transacciones de eventos entre procesos.
   La cola local usa archivos exclusivos y bloqueo de hilos; este incremento valida un solo proceso.

No se autoriza decisión automática ni despliegue productivo con este incremento.
