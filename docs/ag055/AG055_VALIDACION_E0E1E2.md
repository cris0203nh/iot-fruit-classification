# AG-055 — Integración del piloto humano E0/E1/E2 de 117 fotografías

Fecha: 13 de noviembre de 2026, America/Lima. Rama: `feature/AGROP-67-calidad-externa`.
**Integración funcional implementada y probada. Rendimiento independiente E0/E1/E2: no evaluado.**
No se reemplazaron los exploratorios I03 ni el contrato I01; no hubo reentrenamiento,
migración, modificación de la SQLite original, creación de rama ni PR.

## Datos y revisión humana declarada

Se verificaron los dos ZIP de Descargas, sus rutas, las 15 entradas del manifiesto
`SHA256S.txt`, las 117 imágenes decodificables y sus hashes, dimensiones, clases de
carpetas, inventario y registros de entrenamiento. Los scripts/pyc recibidos se conservan
como evidencia y **no se ejecutan**. Las fotografías coinciden por SHA con fuentes SEN/TQ
del paquete anterior; no son nuevas capturas ni prueban variedad Kent.

| Producto normalizado | E0 | E1 | E2 | Total |
|---|---:|---:|---:|---:|
| Mango, variedad no acreditada | 20 | 20 | 21 | 61 |
| Tomate | 20 | 17 | 19 | 56 |

Las 117 etiquetas están registradas en la **cola existente**, con eventos
`human_label_declaration_import`, clase y SHA originales, ZIPs de origen e ID estable.
`reviewer`, `reviewedAt`, `rubricVersion`, evidencia individual y criterios Rxx permanecen
**nulos**, porque no fueron aportados. La fecha de recepción/importación se registra
separadamente y no sustituye la fecha de revisión. No se infiere el nombre del revisor
del perfil del equipo. La plantilla de acta recibida sigue sin completar.

Se reconoce la declaración del usuario de haber etiquetado manualmente las fotos;
no se declara autenticidad/competencia verificada, aprobación de rúbrica ni doble revisión.
`Mango_Kent` se conserva como nombre original de carpeta, no como acreditación varietal.
SEN conserva la licencia CC BY-NC 3.0 y TQ CC BY 4.0 documentadas en los inventarios
anteriores; el uso de mango se mantiene como investigación no comercial.

## Compatibilidad y adaptación de los modelos

Los modelos recibidos son `StandardScaler + SVC(RBF)` de scikit-learn 1.8.0, con 676
rasgos globales. No son compatibles directamente con I01/AG-034 ni con el descriptor
de 57 rasgos de I03. Se adaptaron sin modificar pesos ni entrenar:

- Conversión única mediante deserializador con lista cerrada de clases; rechaza globals
  desconocidos, arrays de objetos y tamaños excesivos. Se usa la versión original 1.8.0.
- Exportación a JSON con scaler, vectores soporte, coeficientes, interceptos, gamma,
  clases y procedencia SHA. **FastAPI no carga joblib/pickle ni requiere scikit-learn.**
- Descriptor auditado equivalente al recibido: imagen completa, incluidos fondo e iluminación.
  No se afirma segmentación ni ROI de entrenamiento verificada.
- Comparación contra los joblib: coincidencia en las **117 predicciones de entrenamiento**;
  diferencia máxima de scores OvR: mango `1,43e-8`, tomate `6,45e-9`.
- Comparación técnica adicional en 40 fotos no usadas por el piloto: 20 por producto,
  misma predicción, diferencia máxima `4,14e-9` y `2,46e-9`, respectivamente.
  Esto prueba la adaptación, **no exactitud ni generalización**: no hay ground truth E0/E1/E2
  independiente para esas fotos.

Contrato nuevo: `ag055-pilot117-svc-rbf-v1`; descriptor `pilot117-global-676-opencv-v1`;
espacio `pilot_declared_e0e1e2`. Los scores mostrados son una normalización softmax de
los scores de decisión OvR, **no probabilidades calibradas**. No hay umbrales de aceptación
validados. Todas las salidas requieren revisión; `independentTestMetrics=null`.

## FastAPI, React y correcciones

Se reutilizaron autenticación, evaluaciones, lectura de fotos, control de integridad,
persistencia idempotente y la cola/eventos append-only de AG-055. No se añadieron tablas.

- `GET /api/evaluations/{id}/vision/quality/pilot/status`: usuario autenticado.
- `POST /api/evaluations/{id}/vision/quality/pilot/analyze`: operador/administrador.
- Consulta de snapshots y `GET/POST .../vision/quality/reviews`: endpoints existentes.

El panel «Piloto E0/E1/E2» muestra propuesta **NO confirmada**, puntuaciones no calibradas,
versión, estado experimental y si el SHA de la foto aparece en entrenamiento. Una foto
no vista por SHA se marca «independencia física sin verificar», nunca prueba independiente.
El piloto usa el producto registrado en la evaluación; no identifica por sí mismo la fruta,
no verifica Kent y no tiene validación de imágenes fuera de distribución.

Las propuestas nuevas tienen `proposedGrade=null` en el snapshot; el grado sugerido
permanece dentro de su espacio experimental. No se escriben `visual_category` ni decisiones
oficiales. Los exploratorios Fresh/Rotten, enfermedades y FGrade siguen separados.

Al abrir una foto que coincide con las declaraciones importadas se muestran clase y
metadatos faltantes. Una corrección autenticada exige confirmación humana/ROI, justificación
y rúbrica; E1/E2 requiere Rxx. Genera otro evento enlazado al importado, sin modificarlo.
Se admite `mango-ext-*` para una rúbrica de mango genérico; se mantiene compatibilidad
con `kent-ext-*`, sin que el prefijo certifique variedad ni aprobación de la rúbrica.

## Similitud, fugas y sesgo de adquisición

Hay **117 hashes de bytes y 117 de píxeles distintos** en el conjunto recibido.
El paquete propone 47 pares similares, tres entre E1/E2. Una auditoría adicional
con método explícito —gris 32×32, DCT 8×8 sin DC, mediana, Hamming de 63 bits ≤8—
encuentra 53 pares, también con tres cruces de clase. Las distancias de 24 pares recibidos
no coinciden con este método; el preprocesamiento pHash del paquete no está especificado,
por lo que se conservan ambos conjuntos como candidatos, sin declarar falsos los originales.

Se agruparon transitivamente relaciones, coincidencias con grupos anteriores y fechas
sugeridas por nombres; el manifiesto de importación tiene 63 componentes técnicos.
La auditoría suplementaria conserva la unión de ambas heurísticas para futuras exclusiones.
**Ningún componente técnico acredita identidad de fruta o sesión.**

Los cruces recibidos incluyen:

- `e1/IMG_20230127_001458.jpg` con `e2/IMG_20230127_001620.jpg` y `e2/IMG_20230127_001648.jpg`.
- `e1/IMG_20230130_024321.jpg` con `e2/IMG_20230127_001620.jpg`.

Inspección descriptiva **de IA, no revisión humana**: el primer par comparte color y fondo,
pero la vista E1 presenta superficie más lisa y una lesión puntual, mientras la E2 muestra
arrugamiento y zona de cáliz/pedúnculo. La similitud global no demuestra misma fruta ni
resuelve severidad. Las etiquetas se conservan y requieren contraste con la rúbrica.

Todas las 117 fotos fueron usadas para entrenar. No existe partición train/val/test del
piloto que permita auditar rendimiento fuera de entrenamiento: no se presenta «ausencia
de fugas» como certificación de generalización. Tomate E0 aparece solo en la fecha aparente
2023-01-04; separar aleatoriamente imágenes o confiar en fondos daría una evaluación engañosa.
Las fechas de nombres no se elevan a sesiones acreditadas.

## Evaluación independiente preparada, aún pendiente

`independent_evaluation_candidates.json` contiene referencias a **40 fotos reales no
usadas por el piloto**, 20 por producto, excluyendo sus hashes y grupos relacionados
conocidos. No duplica fotografías. Se preservan las predicciones de diagnóstico en otro
archivo y se comparó técnicamente su inferencia contra los joblib.

**Cero candidatas tienen actualmente etiqueta E0/E1/E2 independiente e identidad física
acreditadas.** Pueden haber participado en los exploratorios I03: no son una evaluación
independiente del sistema integral. Tampoco se garantiza que no existan relaciones físicas
no detectadas con las 117 fotos.

Antes de medir: confirmar identidad/fruta/sesión y permisos; excluir relaciones nuevas;
presentar imágenes con IDs neutros y ocultar predicción/clase de fuente al revisor;
obtener etiquetas humanas con fecha/rúbrica/evidencia; congelar protocolo y holdout.
El flujo asistido que muestra predicciones no equivale a esa revisión ciega.
Hasta entonces, **accuracy, precision, recall, F1 y matriz de prueba E0/E1/E2 permanecen
no evaluados**. Las coincidencias sobre entrenamiento o entre implementaciones no los sustituyen.

## Pruebas y evidencias reales

Aceptación completa en base SQLite y cola **aisladas**, con fotos reales de ambos productos:

- Backend: **236 aprobadas**, incluidas regresiones AG-053/054 y cuatro tests del piloto.
- Visión: **553 casos: 551 aprobados y dos omitidos** por enlaces simbólicos no disponibles
  en Windows, sin cambiar permisos del sistema.
- Frontend: **113 aprobadas**; TypeScript/Vite build y ESLint de calidad/cliente correctos.
- Chromium real: piloto en mango/tomate, scores, foto/ROI, declaraciones sin revisor/fecha,
  corrección enlazada, reintento idempotente, móvil y coexistencia con los modelos anteriores.
- En la base de ensayo: cinco snapshots (dos pilotos y tres exploratorios), cero grados
  confirmados. Las dos correcciones del navegador están marcadas como pruebas automatizadas,
  no como nuevas revisiones humanas auténticas; las 117 declaraciones originales no se alteran.

Carpeta privada: `%USERPROFILE%\Documents\AgroScan_AG055_E0E1E2_117_01`:
`audit.json`, `manifest.json`, `reviews/`, `models/`, `similarity_audit.json`,
`independent_evaluation_candidates.json`, `adapter_parity_unused_photos.json`,
`acceptance/acceptance.json`, logs completos y `acceptance/browser/` con capturas,
respuestas sanitizadas y resultado real del navegador. `final_validation.json` y
`SHA256SUMS.json` registran la integridad de la entrega. Fotos/modelos permanecen fuera de Git.

## Windows: reproducción y configuración

Desde la raíz, ejecutar la demostración aislada y las suites completas en una salida nueva:

```powershell
$base = "$env:USERPROFILE\Documents"
py -3.13 -m vision.ag055.acceptance_i05 `
  --run "$base\AgroScan_AG055_I03_run02" --i04 "$base\AgroScan_AG055_I04_01" `
  --pilot-run "$base\AgroScan_AG055_E0E1E2_117_01" `
  --output "$base\AG055_piloto_117_repeticion01" `
  --playwright-root "$base\AgroScan_AG055_I04_tools" `
  --chromium "$env:LOCALAPPDATA\ms-playwright\chromium-1248\chrome-win64\chrome.exe" `
  --vision-deps "$base\AgroScan_AG055_I05_tools\python"
```

El ejecutor usa Python original 3.13 para escrituras externas, rechaza puertos ocupados
y detiene sus servidores al terminar. No modifica la base original ni realiza migraciones.
Para una instancia de AgroScan cuyo almacenamiento esté autorizado, los nuevos ajustes son:

```powershell
$env:AGROSCAN_PILOT117_MODELS_PATH = "$env:USERPROFILE\Documents\AgroScan_AG055_E0E1E2_117_01\models"
$env:AGROSCAN_REVIEW_RUN = "$env:USERPROFILE\Documents\AgroScan_AG055_E0E1E2_117_01"
# Mantener AGROSCAN_EXPLORATORY_MODELS_PATH y la política I04 existentes.
# No usar la aplicación fixture ni AGROSCAN_TEST_INSTANCE=1 para revisiones reales.
```

La conversión es una operación única; no es requisito para servir los JSON ya generados.
Si se repite, `vision.ag055.import_pilot117 --help` describe las entradas y requiere una
salida nueva y scikit-learn 1.8.0 en el entorno externo de conversión. No ejecutar `train_pilot.py`
ni cargar los joblib directamente en FastAPI.

## Criterios para AGROP-67

| Criterio | Estado |
|---|---|
| Importar 117 etiquetas humanas declaradas sin inventar metadatos | Cumplido |
| Integrar ambos modelos y conservar exploratorios anteriores | Cumplido |
| Predicción experimental real, scores/versiones y revisión trazable | Cumplido |
| Backend/frontend/build/E2E reales | Cumplido, con omisiones ambientales documentadas |
| Evaluación independiente E0/E1/E2 | Pendiente; cero holdout elegible |
| Revisor/fechas/rúbrica/evidencia originales documentados | Pendiente de aportación auténtica |
| Variedad Kent e independencia física | No acreditadas |
| Calibración, E2→E0 aceptable, estación/cámara y validación externa | Pendientes |
| Ahorro manual, uso productivo o multiworker | No demostrados/no autorizados |

Recomendación: registrar la integración funcional del piloto como completada y mantener
AGROP-67 pendiente de validación experimental externa. La nueva declaración humana sí es
evidencia aportada; no convierte automáticamente el piloto en clasificador acreditado.
