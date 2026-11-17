# AG-034 / AGROP-42 — Incremento 10: perfil de recursos y decisión reproducible

## Objetivo y límite del incremento

Continuación del Incremento 09. Registra el costo de **reglas clásicas univariadas** frente a una **regresión logística L2 ligera**, con los **mismos descriptores** y las **mismas vistas de prueba**, para proporcionar un cuadro experimental documentado que sirva al análisis de alternativas de AG-034.

**No** interpreta el 100 % de acierto mango/tomate como detección de defectos. No entrena E0/E1/E2, no valida máscaras contra un contorno de referencia, no verifica que las tres vistas pertenezcan físicamente a la misma fruta y no acredita el hardware final. El ZIP existente está compuesto por fuentes externas, incluido mango Ataulfo, distinto de la rúbrica Kent.

## Diseño de la medición

1. **Validación de entrada:** CSV del ZIP, rutas, estructura `mangos|tomates/ID/imagen`, hashes SHA-256, duplicados por foto, IDs y grupos fuente, decodificación JPEG/PNG. Sin extraer contenido del ZIP a rutas del sistema.
2. **Partición por ID de fuente declarado:** reutiliza el generador del Incremento 09, semilla 34. En las 90 vistas del dataset actual: 54 de entrenamiento, 18 de validación y 18 de prueba. Ninguna vista del mismo ID se reparte entre particiones. No es una prueba de sesiones físicas independientes.
3. **Preprocesamiento:** las 11 características cromáticas y espaciales de `get_features`; tiempo de lectura/decodificación y extracción por fotografía.
4. **Ajuste:** tiempos de selección de umbral y de optimización logística, siempre **solo con train**.
5. **Inferencia:** sobre las mismas features precomputadas del test, con calentamiento previo, múltiples lotes y mediana/p95 en milisegundos por vista. **No** incluye lectura y extracción.
6. **Pipeline completo:** lectura desde bytes, decodificación, extracción y clasificación, con las mismas imágenes de test para ambos métodos; mediana/p95 en milisegundos por vista.
7. **Memoria:** pico de `tracemalloc` en Python durante el recorrido de test y tamaño serializado JSON. **No mide** memoria RSS total, RAM del dispositivo, VRAM ni microcontrolador.
8. **Decisión:** si ambas exactitudes son iguales y la regla tiene menor mediana de inferencia y menor JSON, conservarla solo como baseline **auxiliar**. En caso contrario, no seleccionar automáticamente. En ningún caso habilitar despliegue comercial.

El orden de ejecución es fijo y los tiempos dependen de caché, CPU, sistema operativo, frecuencias y carga del equipo. No comparar dos plataformas con estos números como si fuera un benchmark controlado del hardware objetivo. Se omiten límites de recursos numéricos: todavía no consta una especificación validada del dispositivo final para esta función.

## Ejecución Windows — desde la raíz de `iot-fruit-classification`

```powershell
$zip = "$env:USERPROFILE\Downloads\AgroScan_Dataset_30_Frutos_90_Vistas.zip"
$salida = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas\AG034_Recursos_Incremento10_01"

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.perfil_recursos_ag034 `
    --zip "$zip" `
    --salida "$salida" `
    --repeticiones 7 `
    --bucles 500 `
    --repeticiones-pipeline 3

.\backend\.venv\Scripts\python.exe -m unittest vision.tests.test_ag034_perfil_recursos_incremento10 -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q
```

**La ruta `--salida` debe ser una carpeta nueva**. No reutilizar nombres existentes; el programa se niega a sobrescribir resultados. No subir las 90 fotografías ni manifiestos externos al repositorio de código sin revisión de derechos y pertinencia.

## Archivos de salida

- `AG034_perfil_recursos.json`: datos fuente, entorno ejecutor, particiones, métricas, latencia mediana/p95, asignaciones Python, advertencias y decisión provisional.
- `AG034_cuadro_comparativo.csv`: dos filas, una por método, apto para incorporar a Jira o al informe académico.
- `AG034_informe_rendimiento.md`: texto generado con las mediciones **del equipo donde se ejecutó**.

## Conclusión para Jira

**Evidencia parcial de AG-034: comparación auxiliar y recursos locales, ejecutada con código reproducible.** Para cierre total según los criterios de aceptación originales faltan anotaciones contrastables sobre atributos externos de mango Kent y tomate, mismas muestras verificadas por sesión física y ensayo en hardware objetivo con límites definidos. No confundir esta entrega con AG-035 (métricas por categoría) ni con aprobación humana de etiquetado.
