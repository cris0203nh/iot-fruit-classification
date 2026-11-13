# AG-055 / AGROP-67 — Incremento 01: clasificación E0/E1/E2 experimental y revisión segura

## Problema observado
YOLOE detecta mango/tomate y segmenta la fruta, pero **no predice E0/E1/E2**.
AG-034 ya dispone de comparación de reglas y softmax por producto con ROI verificada;
no existe dataset acreditado para desplegar un clasificador de condición externa.
AG-036 documentó 30 grupos revisados: 15 tomates E0 (ninguno E1/E2) y mango
con dos E1 y tres E2; insuficientes para partición independiente por tres clases.

## Qué entrega este incremento

1. Reutilización directa del protocolo `vision.evaluation.agrop42.comparar_calidad_ag034`:
   control SHA-256, identidad y sesión, soporte de revisor, ROI revisada, rúbrica,
   agrupación por pieza/sesión, partición entrenamiento/validación/prueba,
   comparación de regla clásica y softmax L2.
2. Exportación separada de modelos *experimentales* por producto solo con datos
   elegibles: `ag055_quality_mango.json` y `ag055_quality_tomate.json`.
3. API autenticada `/api/evaluations/{id}/vision/quality/status`, `/proposals`,
   `/analyze`. Requiere dos fotografías originales y detección YOLOE válida por vista.
4. Salida **bloqueada** cuando no hay artefacto. Con artefacto muestra propuesta
   solo si hay coincidencia entre vistas; las discrepancias exigen revisión.
5. Snapshots append-only con hash del modelo y de fotografías, sin alterar
   `visual_category`, revisiones, estado de evaluación ni archivos originales.
6. Panel en captura e historial de trazabilidad para mostrar estado y propuesta.

## Restricciones obligatorias

- **No** activa clasificación automática de producción ni cambia un grado humano.
- Una propuesta del modelo experimental **no** es verdad de referencia.
- Los scores softmax **no** son probabilidades calibradas.
- Entrenamiento usa ROI revisada; inferencia online usa caja detectada YOLOE.
  Existe *domain shift* que debe medirse antes de aprobar el modelo.
- Las rúbricas `kent-ext-*` y `tomato-ext-*` requieren aprobación externa.
- Para mango, confirmar que la variedad objetivo sea Kent; YOLOE detecta mango
  genérico y no verifica la variedad.
- No hacer equivalencia entre categoría comercial «primera/segunda» y E0/E1/E2.
- El despliegue productivo requiere umbrales decididos y validados **por clase**, por
  producto y por escenario de cámara, además de revisión humana y auditoría.

## Entrenar con datos reales auditables (desde raíz del repo)

El archivo oficial está en `vision/evaluation/agrop42/AG034_plantilla_calidad_externa.csv`.
No alterarlo ni inventar etiquetas. Crear carpeta local FUERA de Git con las imágenes
originales y soportes del revisor. Para la auditoría de una plantilla vacía se puede
utilizar el propio CSV de plantilla y carpetas existentes para imágenes/soportes.

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$trabajo = "$env:USERPROFILE\Documents\AgroScan_Calidad_Real"
# Colocar allí datos reales previamente reunidos; no crear registros ficticios.
& $py -m vision.ag055.quality_model `
  --csv "$trabajo\etiquetas.csv" `
  --imagenes "$trabajo\imagenes" `
  --soportes "$trabajo\soportes" `
  --salida-informe "$trabajo\auditoria_ag055.json" `
  --exportar-modelos "$trabajo\modelos_experimentales"
```

**No instalar modelos si el reporte dice `blocked_insufficient_data`**.
Los directorios de salida deben existir y el comando **nunca sobrescribe** archivos.
Para usar un modelo experimental con la API, configurar variable de entorno
`AGROSCAN_QUALITY_MODELS_PATH` con una carpeta local conteniendo
`ag055_quality_mango.json` y/o `ag055_quality_tomate.json`.
No subir pesos, imágenes, soportes ni etiquetas personales al repositorio.

## Estado de cierre

- Software de experimentación y revisión asistida: desarrollado.
- Modelo de grados con rendimiento acreditado: **pendiente de datos elegibles**.
- Decisiones automáticas finales: pertenecen a AG-056; **no autorizadas aquí**.
- Hardware / validación con mango y tomate reales: pendiente.
- Cierre formal de AG-055: pendiente de entrenamiento y evaluación independientes.
