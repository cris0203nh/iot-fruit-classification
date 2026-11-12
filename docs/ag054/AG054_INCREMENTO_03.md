# AG-054 / AGROP-66 — Incremento 03

## Calibración adaptada a la plataforma real y validación dimensional

**Estado:** software implementado; validación física y metrológica pendientes.

### 1. Diseño de referencia

- Balanza real: celda WSS-5KG, amplificador HX711 y discos circulares transparentes.
- La fruta puede sobresalir **si permanece totalmente sostenida por el disco móvil** y no toca otras superficies.
- Webcam USB **fija y vertical**, apuntando desde arriba, sin contacto con la balanza.
- Marco ArUco **independiente de la celda de carga**, con marcador/es en plano físico a la altura superior del disco, sin contacto con el disco ni la fruta.
- Tablero v1: `Tablero_AG054_A3_390x275mm.svg`, página A3 horizontal (420 × 297 mm), cuerpo 390 × 275 mm.
- ArUco `DICT_4X4_50`, IDs 0, 1, 2, 3; cuadrados negros exteriores de lado **40 mm**.
- Coordenadas **desde la esquina superior izquierda del cuerpo del tablero**, en milímetros:
  - 0: (15, 15)
  - 1: (335, 15)
  - 2: (335, 220)
  - 3: (15, 220)
- Orificio central previsto: diámetro 228 mm, **guía de montaje**, no sustituto de la verificación física. Si la plataforma/fruta no cabe sin tocar el marco, no instalar ese marco como está: es necesario rediseñar físicamente el soporte, conservar posiciones geométricas de los marcadores o registrar un nuevo layout/versionado de software.

**Impresión:** papel A3, escala 100 %, sin «ajustar a página». El área física de los marcadores y las distancias entre ellos deben medirse con una regla/calibrador. Una alternativa es usar las tarjetas A4 `Marcadores_ID0-3_A4_40mm.svg` montadas en un soporte rígido a las coordenadas anteriores. No colocar las tarjetas en posiciones arbitrarias.

### 2. Algoritmo integrado

1. Reutilizar la fotografía original y la geometría YOLOE ya persistidas en AG-054 I01.
2. Verificar integridad SHA-256 del original, que pertenece a la evaluación y al producto registrados.
3. Reconocer ArUco 4x4_50 IDs 0–3 con OpenCV; exigir **al menos 3 distintos** y cobertura espacial en dos direcciones.
4. Rechazar marcas recortadas, pequeñas, deformadas, duplicadas o invadidas por la máscara de la fruta.
5. Rechazar fruta parcialmente fuera de encuadre o fuera del área geográfica calibrada.
6. Calcular homografía imagen→plano del tablero mediante RANSAC; medir RMS residual en mm contra las esquinas físicas del patrón. Umbral interno de coherencia RMS <=1.5 mm (criterio de consistencia geométrica del patrón, **no garantía de precisión 3D**).
7. Transformar el contorno de la fruta al plano del tablero y calcular ancho, alto, eje mayor, eje menor, área, perímetro; **salida `cm_reference_plane` únicamente**.
8. Guardar un snapshot idempotente por fotografía, hash, versión de la geometría y reglas; conservar el original inalterado.
9. Permitir a operador registrar medidas de esa misma fruta obtenidas con calibrador físico; registrar errores absolutos/porcentuales y un informe agregado de comparaciones, sin emitir aprobación automática.

### 3. API

- `GET /api/evaluations/{evaluationId}/vision/board/{imageId}`: lista de estimaciones, autenticación.
- `POST /api/evaluations/{evaluationId}/vision/board/{imageId}`: requiere rol operador, YOLOE medido y declaraciones explícitas de montaje.
  ```json
  {
    "boardVersion": "ag054-board-a3-v1",
    "markerAtPlatformLevel": true,
    "independentSupport": true,
    "printedDimensionsVerified": true,
    "fixedCamera": true
  }
  ```
- `GET /api/evaluations/{evaluationId}/vision/board/{imageId}/comparisons`: consultas de comparaciones, autenticación.
- `POST /api/evaluations/{evaluationId}/vision/board/{imageId}/comparisons`: requiere operador, estimación aceptada y medidas manuales con instrumento identificado.
  ```json
  {"referenceMajorCm": 10.5, "referenceMinorCm": 7.8, "instrumentId": "Pie de rey / identificador real"}
  ```
  Valores del ejemplo **no corresponden a una fruta medida**.
- `GET /api/evaluations/vision/board-validation/report`: agregado descriptivo por producto, acceso revisor/admin, no estima exactitud sobre universo de piezas.

### 4. Compatibilidad y límites

- Migración Alembic `a054d3e4f506`, descendiente de `f054c2b3a4d5` (I02).
- Tablas nuevas: `ag054_board_calibrations`, `ag054_dimensional_comparisons`.
- No se alteran lotes, piezas, evaluaciones, evidencias originales ni firmware WSS-5KG/HX711.
- No se declara que una imagen monocular contenga altura, volumen, tamaño 3D ni diámetro real exacto.
- El RMS del patrón no mide error en dimensiones de fruta: superficies fuera del plano introducen paralaje. Tampoco se ha calibrado distorsión intrínseca de la webcam.
- Las decisiones E0/E1/E2 **no** se generan aquí.
- El `report` registra comparaciones (puede haber varias por pieza); no certifica una muestra representativa ni cuenta piezas únicas.
- Las declaraciones en UI son responsabilidad del operador: **el software no verifica físicamente** que marco, plataforma o cámara estén inmóviles ni que el mango no toque la mesa.
- Si los 3 marcadores no se observan, se retiene solo la medida en píxeles y se devuelve `needs_review` sin cm.

### 5. Protocolo de campo pendiente

1. Construir soporte rígido para webcam/marco, aislado de celda y plataforma. Comprobar peso con/ sin marco y al cargar el fruto.
2. Imprimir tablero, verificar las distancias reales y registrar fotos del montaje. Montarlo al nivel de la plataforma; confirmar que fruta no hace contacto con el marco.
3. Fijar webcam (misma resolución, zoom, enfoque, distancia e iluminación por sesión) y registrar esos parámetros. Si cambian, repetir ensayo.
4. Procesar varias frutas de tamaños diferentes de mango y tomate (propuesta experimental inicial: al menos 10 piezas distintas por producto, más repeticiones para estimar repetibilidad; el tamaño definitivo de muestra y tolerancia deben definirse antes del ensayo).
5. Fotografiar fruto completo con tablero visible; evaluar proyección en cm. Medir físicamente ejes mayor/menor con calibrador y registrar instrumento y operador.
6. Evaluar sesgo, MAE, error porcentual absoluto y dispersión por fruta, tamaño y posición; distinguir proyecciones del plano de dimensiones físicas.
7. Verificar estabilidad y carga excéntrica WSS-5KG/HX711 con masa patrón: centro, lados y posiciones delantero/trasero. **No aceptar un valor de peso si la celda está sobrecargada, rozando, inestable o con apoyo externo.**
8. Documentar limitaciones y establecer criterios de aceptación *antes* de declarar metrología física validada. Si el sesgo es alto, usar método de profundidad/segunda vista calibrada o corrección empírica validada sobre muestras independientes.

**Estado de validación en esta entrega:** pruebas de software con marcadores y contornos sintéticos; no se han medido frutas reales, no se ha probado la webcam definitiva, la balanza física ni su excentricidad.
