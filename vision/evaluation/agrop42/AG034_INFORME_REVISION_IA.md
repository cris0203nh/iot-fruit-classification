# AG-034 / AGROP-42 — Revisión visual de 90 vistas y contraste experimental acotado

**Fecha de elaboración:** 5 de noviembre de 2026. **Proyecto:** AgroScan, PFCIII. **Tipo de revisión:** asistida por IA; no es una aprobación humana ni un dictamen agronómico. **Código y evidencias:** `benchmark_producto_ag034.py`, `AG034_revision_visual_90_vistas_IA.csv`, `AG034_resumen_30_ejemplares.csv`, `AG034_benchmark_auxiliar.json`.

## 1. Criterio real de AG-034

De acuerdo con el backlog del equipo, **[AG-034] Comparar enfoque de reglas clásicas y modelo ligero si hay datos suficientes**, cuyo criterio de aceptación es comparar los métodos sobre el mismo conjunto de prueba, considerar límites de hardware y seleccionar una alternativa con justificación. Debe quedar como evidencia un cuadro experimental y código. **Este informe no autoriza declarar como completado el objetivo de comparar la clasificación de atributos externos E0/E1/E2.**

## 2. Materia prima y revisión de integridad

- ZIP estudiado: `AgroScan_Dataset_30_Frutos_90_Vistas.zip`, con `trazabilidad.csv`, 15 IDs de mango, 15 IDs de tomate, y tres vistas por ID: **90 fotografías**.
- Se cotejaron **90/90** SHA-256 de la trazabilidad con los archivos originales del ZIP; sin duplicados exactos en los identificadores declarados.
- Los archivos corresponden a **fuentes públicas externas**. El archivo declara mango **Ataulfo**, no Kent, y tomates de Fruits-360. Los identificadores y secuencias declaradas **no demuestran identidad física ni independencia de captura en AgroScan**; pueden usarse como grupos de fuente para evitar repartir tres vistas entre entrenamiento y prueba, pero no como evidencia de validación de campo.
- Se inspeccionaron visualmente las **90 imágenes y sus máscaras candidatas reconstruidas con el pipeline del Incremento 08**. Se conservaron montajes de comparación original/resultado para trazabilidad. Se detectan rasgos visibles (color, forma, marcas) sin derivar automáticamente diagnóstico de defecto, madurez o calificación comercial.

## 3. Dictamen de revisión de máscaras, asistido por IA

| Producto | Vistas | Propuesta compatible visualmente | Parcial | Sin máscara | No utilizable |
|---|---:|---:|---:|---:|---:|
| Mango Ataulfo | 45 | **35** | 0 | **10** | 0 |
| Tomate | 45 | **27** | **15** | 0 | **3** |
| **Total** | **90** | **62** | **15** | **10** | **3** |

La palabra **compatible** significa que, en inspección visual de la imagen reducida y de la superposición provisional, la región cromática propuesta cubre aproximadamente la forma aparente del fruto. **No equivale a una máscara de referencia delineada por un humano ni a un dato validado para entrenar o calcular IoU/Dice.** Los errores de borde, oclusión y píxeles excluidos pueden persistir incluso en las 62 consideradas visualmente compatibles.

**Incidencias observadas:**

- **MANGO_01 a MANGO_05, vistas 1 y 2:** 10 imágenes sin candidato debido al supuesto de fondo neutro; la vista 3 de esos IDs produce máscara candidata.
- **TOMATE_04, TOMATE_05, TOMATE_07, TOMATE_11, TOMATE_14:** 15 máscaras parciales, con pérdida evidente de zonas oscuras de la fruta.
- **TOMATE_15:** las tres vistas presentan segmentación no utilizable para una máscara completa (zona superior/pedúnculo u ausencia de candidato).
- **TOMATE_12 a TOMATE_15:** 12 fotografías con resolución de 100×100 píxeles; no son evidencia suficiente para inspección de defectos finos. Algunas pueden servir para descripción cromática limitada.
- **MANGO_07, MANGO_08, MANGO_15, TOMATE_02, TOMATE_04 y TOMATE_05**, entre otros: manchas, líneas, áreas oscurecidas o irregularidades visibles que deben revisarse con las rúbricas específicas. **No se asignaron E0/E1/E2**, ni se diagnosticaron enfermedades.

El CSV de 90 filas detalla por foto el origen, el hash, el estado del pipeline, la observación IA y las limitaciones de aprobación. La responsabilidad de revisar físicamente una muestra, declarar la adecuación agronómica y firmar una etiqueta de calidad sigue siendo del operador o especialista designado.

## 4. Comparación experimental auxiliar: *tipo de producto*, no defectos

Para ofrecer una evidencia reproducible de la mecánica de comparación en AG-034, se ejecutó un **experimento auxiliar** de discriminación binaria «mango frente a tomate». Se utilizaron **solo etiquetas de tipo de fruto** provenientes del inventario y corroboradas visualmente. **Este experimento no es una comparación de clasificación E0/E1/E2, deterioro ni conformidad comercial.**

### Protocolo

- Mismos **90 archivos** originales para extraer características de color y ocupación cromática.
- Partición agrupada por `(producto, id_ejemplar)`, nunca por vista: **9 IDs por producto para entrenamiento, 3 para validación y 3 para prueba**. Corresponden a **54/18/18 imágenes**, respectivamente; ninguna vista de un mismo ID fuente cruza particiones.
- **Reglas clásicas:** un único atributo y umbral seleccionados **solo sobre entrenamiento**. El mejor atributo fue la proporción de píxeles cromáticos de la fotografía, con umbral aproximadamente **0,33577**; esto alerta de que el procedimiento puede identificar el *tipo de encuadre/fuente*, no rasgos intrínsecos robustos del producto.
- **Modelo ligero:** regresión logística L2, **12 parámetros** (11 pesos y un sesgo), ajustada exclusivamente sobre entrenamiento. Utiliza los mismos 11 descriptores disponibles para ambos enfoques y exportación JSON, sin dependencias pesadas o serialización insegura.
- Se evaluaron ambos sobre **las mismas 18 vistas de prueba**, correspondientes a 6 IDs de fuente (3 mango, 3 tomate). Las etiquetas de prueba no se usan para ajustar modelos o umbrales.

| Indicador sobre prueba común | Regla clásica | Regresión logística ligera |
|---|---:|---:|
| Vistas de prueba | 18 | 18 |
| IDs de fuente en prueba | 6 | 6 |
| Aciertos identificando mango/tomate | **18/18** | **18/18** |
| Exactitud **solo en identificación de producto** | **100 %** | **100 %** |
| Inferencia promedio por vista, CPU del entorno de análisis (excluye extracción) | ~0,00013 ms | ~0,00106 ms |

**Advertencia principal sobre el resultado 100 %:** las dos especies proceden de **repositorios fotográficos distintos** con encuadres y fondos característicos. La fracción cromática separa probablemente dominios de captura, de modo que esa exactitud **no debe extrapolarse a fotografías capturadas por AgroScan, clasificación de defectos, nuevos lotes o variedades**. El conjunto de prueba fue independiente por ID dentro del mismo origen, no independiente por proveedor de fotografías o entorno físico.

Se midió adicionalmente una mediana de **~30,03 ms por imagen** para extraer descriptores en el equipo que ejecutó este ensayo (Pillow, CPU; resolución interna redimensionada a 112 px). El pico observado por `tracemalloc` fue **3,14 MiB en asignaciones Python**: no es la memoria RAM total de la aplicación ni una prueba en ESP32. Los tiempos son puntuales y dependientes de hardware; deben repetirse en la estación final antes de afirmar cumplimiento de los límites de hardware.

**Decisión auxiliar:** conservar la regla cromática como control de referencia por simplicidad y costo de inferencia; **no desplegarla como clasificador comercial ni como clasificación de fruta robusta**, porque explota información potencialmente dependiente del dataset. El modelo ligero queda como contraste metodológico experimental, no como modelo de defectos validado.

## 5. Evaluación de cierre de AG-034

| Condición | Veredicto y evidencia |
|---|---|
| Revisión visual de material disponible | **Realizada por IA** en 90 imágenes, trazable a SHA-256. No es firma humana ni etiqueta E0/E1/E2. |
| Comparación «reglas vs modelo ligero» en el mismo test | **Ejecutada solamente para identificación de tipo de fruto**, con partición por ID, código y cuadro experimental. |
| Comparación de atributos externos de mango Kent y tomate | **No acreditada**: fuentes de mango Ataulfo, sin anotaciones E0/E1/E2 revisadas. |
| Límites de hardware de estación final | **No acreditados**: se dispone de perfiles locales de CPU, no de pruebas físicas del dispositivo final. |
| Selección de alternativa para producción | **No acreditada**; selección auxiliar de un baseline de referencia sin validez comercial. |
| Estado recomendado en Jira | **En curso / parcialmente desarrollado**, no `Done` para la interpretación original de AG-034. |

### Trabajos mínimos para acreditar cierre íntegro

1. Obtener imágenes **Kent** si se exige esa rúbrica; disponer para ambos productos de anotaciones E0/E1/E2 o atributos externos aplicables, con criterio e identidad de sesión confirmados y revisión firmada.
2. Rehacer la comparación de reglas y modelo ligero sobre el **mismo conjunto independiente de prueba por pieza y sesión**, con métricas del objetivo real, casos dudosos y evaluación en el hardware de la estación. Si no existen datos suficientes para entrenar un modelo ligero, documentar formalmente esa decisión y acordar con el responsable de la actividad el cierre condicional sin atribuirle métricas inexistentes.

> **Conclusión:** el asistente sí realizó la revisión visual técnica solicitada, registró deficiencias de máscaras y comparó ambos enfoques en un problema auxiliar verificable; **no puede aprobar por sí solo una revisión humana o dar por terminada la clasificación comercial AG-034** sin los datos y ensayos faltantes.
