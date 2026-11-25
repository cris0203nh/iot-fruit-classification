# Clasificación E0/E1/E2 — diagnóstico general DEV (23/11/2026)

**Dictamen: PARCIAL.** Corregidos controles de evidencia, caché y diagnóstico. El modelo actual no admite cualquier encuadre del tablero: ampliar su dominio mediante recortes YOLOE exige una nueva versión de preprocesamiento/modelo y validación. No se reentrenó ni se reemplazaron pesos. No se acredita exactitud comercial.

## Causa y contrato del modelo

Captura guarda fotografías por organización; el precheck identifica mango/tomate mediante YOLOE. AG-054/ArUco y calidad son ramas independientes. Una geometría válida no demuestra que AG-055 haya segmentado correctamente ni valida E0/E1/E2.

`train_v2.py` y `v2.py` comparten `features(raw)`: imagen completa orientada por EXIF, reducción máxima a 320 px, GrabCut determinista, núcleo cromático y contorno rellenado. Se exige componente mínimo del 8 % del encuadre, área máxima 85 % y solidez mínima 0,94. Los marcadores/papel/sombras no quedan excluidos mediante identidad semántica; el método es heurístico y puede fallar con objetos pequeños, colores neutros, otros objetos o formas irregulares. No se redujeron esos umbrales.

Descriptor de 128 atributos: histogramas RGB/HSV/gris, gradientes interiores y mediana/IQR. Orden y dimensión, normalización, escalado entrenado mediana/IQR con piso 0,05, SVC RBF, votos y etiquetas `E0,E1,E2` permanecen intactos. Los scores no son probabilidades calibradas. No se usa YOLOE como clasificador de calidad.

Artefactos instalados verificados con SHA256SUMS y contrato `ag055-v2-masked-svc-v1` / `fruit-mask-s40-solidity094-128-hsv-s32-robust-floor005-v1`:

- Mango: `17b59e4faf1b183d263107789cdfdb881b040899a1b335a9610454f427fac2f4`.
- Tomate: `113957046c1c16e50d42e8bc79203322b2ed733b16d601497ce17dda04e2aa7f`.

No hay dos implementaciones distintas de entrenamiento/inferencia para V2 en el código. Sí existe un cambio de dominio entre sus imágenes de desarrollo y las nuevas capturas del tablero. Además, el entrenamiento documentado usó OpenCV 5.0.0 y DEV tiene 4.12.0: no se atribuye automáticamente el rechazo a esta diferencia. El manifiesto/corpus V2 no está disponible en su ubicación privada documentada para repetir la paridad completa de entrenamiento. El modelo I01 anterior es otro contrato, con advertencia propia de ROI manual frente a automática; no se utilizó como escape para forzar grados.

## Correcciones compatibles

- FastAPI verifica presencia de una sola fruta, producto, confianza y máscara con el detector existente antes de V2. Conserva **la imagen completa** para el descriptor entrenado. Ausencia, ambigüedad y máscara insuficiente generan abstenciones explícitas. Fallo transitorio del detector responde 503 sin guardar una predicción irrecuperable en caché.
- Tamaño validado antes de decodificar píxeles; fotografías corruptas o fuera de dimensiones admitidas producen motivos por vista, sin perder el análisis de las otras. Se comprueba dimensión/finitud del descriptor antes del SVC.
- El rechazo por componente pequeño incluye fracción medida y mínimo exigido. No se presenta como falta de detección ni como discrepancia entre grados.
- Política `ag055-v2-detection-input-guards-v2` en status, fingerprint y snapshots; React invalida solo el caché de inferencia de política anterior. Reanálisis añade un registro y respeta la idempotencia. Los snapshots históricos siguen consultables, sin sobrescritura ni migración.
- Captura, resultados, historial y herramientas de revisión muestran motivos específicos. Solo hay discrepancia de grados cuando las predicciones evaluables realmente discrepan. Sin propuesta verificable se conserva revisión humana y grado consolidado nulo.
- Se mantuvo el botón de dimensiones tras autorización para retirar una edición simultánea `false && ...`; no cambió el algoritmo ArUco.

## Evidencia real antes/después

Se leyeron las 15 imágenes DEV autorizadas, sin modificar originales: **7 hashes distintos**, 14 registros tomate y uno mango; no acreditan 15 frutas independientes. Ninguno coincide en bytes con los hashes de entrenamiento, pero eso no prueba independencia física ni aporta etiquetas humanas. I-000014/I-000015 son diagnóstico; el resto son regresión técnica. No se empleó un test independiente para ajustar umbrales ni se consultaron las 40 fotografías reservadas históricas. No hay un conjunto local independiente etiquetado con el que certificar generalización.

| Caso | Antes | Después |
|---|---|---|
| 12 registros tomate segmentables | Propuesta E0 | E0; puntuaciones idénticas |
| Un registro mango segmentable (una vista) | Propuesta E2 | E2 por vista; no permite consolidación de dos vistas |
| I-000014 | `fruit_not_separated` | `insufficient_fruit_area_in_frame`: componente 6,7435 %, mínimo 8 % |
| I-000015 | `fruit_not_separated` | `insufficient_fruit_area_in_frame`: componente 6,8216 %, mínimo 8 % |

YOLOE detectó una fruta compatible en los 15 registros (CPU, sin simulación). Un diagnóstico general con su bbox permitió extraer características de los 15 recortes; **no se ejecutó SVC sobre esos recortes**, porque cambian el preprocesamiento entrenado. No es prueba de una mejora de exactitud.

FastAPI ASGI se ejecutó sobre copia privada de DEV en nueve evaluaciones, con inferencia real, repetición idempotente y conservación de siete snapshots anteriores. Los resultados reales de seis evaluaciones con dos vistas pasaron por las funciones/componentes React existentes mediante SSR. Esto no sustituye una sesión visual de navegador, una captura nueva de cámara ni una prueba física de hardware.

Todos los contenidos de tablas DEV, las 15 fotografías y los artefactos YOLOE/prompts/V2 se verificaron sin cambios. Solo la copia recibe nuevas propuestas. No se tocó QA, la base histórica, COM-07/08, SMTP, suscripciones, firmware ni autenticación.

## Verificaciones ejecutadas

- Backend completo: `python -B -m unittest discover -s backend/tests -p 'test_*.py'`: **577 casos, 574 aprobados y 3 omisiones preexistentes**.
- Visión completa: `python -B -m unittest discover -s vision/tests -p 'test_*.py'`: **576 casos, 574 aprobados y 2 omisiones preexistentes**.
- Frontend: `npm test` con `AGROSCAN_INFERENCE_EVIDENCE` apuntando al informe real privado: **234/234 aprobados**, sin omisiones.
- Regresiones frontend I02–I05: **62/62**, incluyendo adquisición, dimensiones, evidencia e historial. `npm run lint` y `npm run build`: correctos; permanece el aviso de bundle >500 kB.
- Software: posiciones/tamaños/colores, máscaras pequeñas, corrupción, atributos incompatibles, E0/E1/E2 mediante fixtures explícitos, abstenciones, detección incorrecta, outage recuperable, caché por política, revisión y snapshots inmutables. Los fixtures no son entrenamiento ni evidencia experimental de E1. No hay E1 humano independiente en las muestras reales utilizadas.

Informes y fotografías privados no se incorporan a Git. Evidencia de esta ejecución: `Documents/AgroScan-Private-Backups/vision-general-20261123-200316` (`before.json`, `yolo-diagnostic.json`, `real-inference.json` y logs de suites). Las omisiones existentes requieren evidencia física/experimental autorizada o symlinks de Windows; no se añadieron omisiones para ocultar fallos.

## Bloqueo y siguiente validación necesaria

El modelo actual puede generar propuestas en nuevas imágenes **dentro de sus condiciones**, pero no puede prometer clasificación para el tablero a cualquier distancia, posición o iluminación. Para normalizar mediante ROI sin reutilizar indebidamente estos pesos:

1. Congelar detector/prompts, recorte completo con margen definido, tratamiento de bordes, máscaras, resolución y descriptor bajo **nueva versión**. Verificar las máscaras con personas; sombras, marcadores y reflejos requieren evidencia real, no solo área/solidez.
2. Recoger capturas reales representativas por producto y E0/E1/E2, además de no evaluables, con tamaños, posiciones, ángulos, distancias e iluminación variados. Necesarios rúbrica aprobada, revisor, fecha y procedencia. No usar predicciones como ground truth ni inventar Kent.
3. Separar desarrollo y test antes del ajuste, agrupando fruta física, sesiones, vistas y duplicados. Incluir E0 tomate en sesiones independientes: el desarrollo anterior tenía esa clase en un único grupo y no acreditaba su validación interna completa. No reutilizar como test nuevo material ya inspeccionado.
4. Ajustar escalador/SVC y cualquier calibración solo en desarrollo; exportar y verificar paridad y hashes del artefacto nuevo. Medir cobertura/abstenciones, matriz por clase/producto, errores graves y rendimiento por sesión en el test congelado. Mantener los rechazos en el denominador y la revisión humana. No se fija un tamaño muestral suficiente sin diseño estadístico.

Sin esos datos, entrenar para que estas dos fotografías obtengan E0/E1/E2 sería fabricar una solución particular. La generalización y la exactitud experimental permanecen bloqueadas, no las comprobaciones técnicas documentadas.
