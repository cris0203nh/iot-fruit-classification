# AG-054 / AGROP-66 — Incremento 02: medición calibrada de proyección 2D

## Equipo de referencia

- **Sensor de masa:** WSS-5KG, barra de carga nominal 5 kg, lectura mediante HX711 y el firmware existente. **No mide dimensiones ni profundidad.**
- **Cámara:** webcam USB fija, vista superior aproximadamente perpendicular a la plataforma.
- **Objeto:** mango o tomate sobre plataforma; puede sobresalir suspendido **sin tocar otra superficie**. Debe permanecer completamente dentro del campo visual.
- **Marcador:** ArUco DICT_4X4_50, ID 0, lado exterior negro **medido físicamente**. Plantilla incluida `Marcador_ArUco_ID0_50mm.svg`, que se debe imprimir a **escala 100 %** y medir con regla/calibrador. No confiar solo en el nombre «50 mm».
- Colocar el marcador en un soporte **estable e independiente**, de altura equivalente a la plataforma de pesaje, de modo que no agregue peso ni roce el mango. No ponerlo simplemente sobre una mesa más baja. Mantener la referencia visible, sin taparla con la fruta.

## Alcance implementado

El endpoint POST `.../api/evaluations/{E-ID}/vision/physical/{I-ID}` recibe:

```json
{"markerId":0,"markerSideMm":50.0,"markerAtPlatformLevel":true}
```

Precondiciones: autenticación de operador/admin, fotografía persistida, geometría YOLOE válida en la misma evaluación, SHA-256 del original, tamaño de referencia declarado, plano del marcador declarado. Reutiliza máscara existente: **no vuelve a ejecutar YOLOE**. Detecta ArUco en la fotografía original y transforma el contorno a un plano con homografía (OpenCV). Persistencia idempotente; registro inmutable por imagen, geometría, tamaño y versión de reglas. GET autorizado a operador, revisor o administrador. El original no se sobrescribe.

Entrega proyección de ancho/alto/ejes en centímetros del **plano de referencia**, área cm² y perímetro cm. No es estimación calibrada de la dimensión 3D real de la fruta y no hay corrección de la altura de la fruta ni de distorsión de lente. `physicalDimensionsValidated=false` y `fruitHeightCorrected=false` siempre. Si marcador ausente, oculto, recortado, demasiado pequeño o la fruta sale del encuadre: resultado `needs_review` sin métricas inventadas.

## Integración funcional

En Captura, Historial y Trazabilidad la evidencia geométrica muestra una sección **«Escala de referencia ArUco»**: se introduce lado físico medido del marcador (mm) y se confirma el plano; el frontend recupera la medición persistida, muestra los valores en cm de referencia y el marcador delimitado en azul. Al cargar una fotografía antigua sin marcador, la operación retorna «Marcador no detectado» y no inventa cm. La imagen original permanece protegida.

## Limitaciones y criterios para validación física

1. **Una sola cámara monocular no recupera por sí sola dimensiones 3D reales.** La fruta está elevada respecto al marcador y su contorno presenta distintas profundidades. La homografía solo es estrictamente válida para puntos coplanares; su extrapolación hacia el contorno produce sesgo. Los valores de cm se etiquetan como estimados en el plano de referencia.
2. Antes de aceptar cm como tamaño real, calibrar intrínsecos/distorsión de webcam (preferiblemente ChArUco), medir la geometría efectiva de la fruta o introducir información de profundidad validada y contrastar medidas reales de muestras diversas con calibre físico. Documentar error absoluto/relativo, sesgo, variabilidad por clase/tamaño y criterio de aceptación definido por equipo. Hasta entonces `physicalDimensionsValidated=false`.
3. La WSS-5KG de 5 kg es un sensor de masa; el HX711 no permite detectar si una fruta toca la mesa. Validar montaje, tara, pesos patrón, estabilidad y **cargas descentradas** en posiciones periféricas. El peso bruto soportado no debe sobrepasar la capacidad nominal; no asumir precisión metrológica por el nombre del sensor. El software de este incremento **no modifica** la lógica de peso/firmware.
4. Si el mango sobresale de la plataforma, debe permanecer suspendido sin apoyos externos ni contacto con los bordes, soportado solo por la celda/plataforma. El control físico es responsabilidad del montaje y verificación del operador.
5. La selección de marcador ID0 y escala manual declarada no acredita por sí misma su longitud física ni que la cámara esté fija. Se guarda para trazabilidad como dato declarado; la validación física requiere evidencia adicional.

## Verificaciones de software

- `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_ag054_planar_calibration.py" -v`
- `cd frontend && npm test && npm run build`
- `cd backend && .\.venv\Scripts\python.exe -m alembic current && .\.venv\Scripts\python.exe -m alembic heads`
- Crear **una copia SQLite** mediante el script `AG054_I02_Respaldo_DB.py` antes de `alembic upgrade head`. Migración `f054c2b3a4d5` depende de `e054a1b2c3d4`; solo crea nueva tabla e índices.
- Validación futura con marcador físico medido y webcam fija: foto real, medición en cm de referencia, resultado persistido, revisión visual y contraste con calibre físico. No declarar acreditada la medición 3D antes de ese ensayo.
