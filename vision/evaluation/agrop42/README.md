# AGROP-42 [AG-034] — Incremento 01: auditoría de datos y viabilidad

El objetivo es verificar **si es posible iniciar una comparación válida entre reglas clásicas y un modelo ligero**. Este incremento **no** entrena, compara predicciones, genera métricas de rendimiento ni edita AGROP-39/40/41.

## Entradas y política de evidencias

- `backend/data/agroscan.db` — SQLite local, leído en modo **solo lectura** (el proyecto no versiona esta base).
- `backend/data/images/` — los archivos de imagen se identifican por la ruta relativa de la tabla `images` (raíz `backend/data`).
- `--manifests-dir` (opcional) — busca objetos JSON con `piece` e `images`. Abarca manifiestos de AGROP-40/41, pero no confunde sus informes JSON con nuevas capturas. Para la independencia por sesión, el manifiesto debe aportar `images[].capture.device_id` y `boot_id`. Si faltan, las imágenes siguen apareciendo en el inventario, **no** como grupos independientes para entrenamiento.
- `--annotations` (opcional) — archivo JSON con `annotations`, cada elemento con SHA256 de una imagen *real*, `product` (`mango`/`tomate`), `label` (`E0`/`E1`/`E2`), `review_verified: true`, `reviewer_id`, `reviewed_at` y `rubric_version`. Es una **declaración de revisión documentada**, no acreditación externa de un experto. La rúbrica vigente debe confirmarse por separado; el sistema no valida su aprobación.

Las etiquetas `evaluations.visual_category` y `operator_visual_label` se **cuentan como no verificadas** y nunca como ground truth para una comparación supervisada. No se infiere identidad de un fruto por color o caja de detección.

## Ejecución en Windows (desde raíz del repositorio)

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r vision/requirements.txt

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar `
  --manifests-dir vision/experiments `
  --output vision/experiments/AGROP42/auditoria_viabilidad.json

$r = Get-Content vision/experiments/AGROP42/auditoria_viabilidad.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.totales
$r.por_producto.mango | Select-Object status, imagenes_unicas_sha256, grupos_independientes_verificables, motivos
$r.por_producto.tomate | Select-Object status, imagenes_unicas_sha256, grupos_independientes_verificables, motivos
```

Si solo quieres auditar el origen principal, **omite** `--manifests-dir`. La omisión se refleja en `fuentes.manifiestos.status=no_solicitado`, no en una afirmación de que no existen manifiestos.

El informe se escribe en `vision/experiments/`, excluido por `.gitignore`; evita publicar fotografías, rutas o datos locales. El reporte incluye hashes SHA256 y referencias de registros: revisa los permisos antes de compartirlo.

## Qué se audita

1. Integridad del archivo PNG/JPEG, ruta bajo raíz permitida y SHA256 del contenido real; nunca deduplicación por nombre. SHA256 no detecta copias redimensionadas, recortadas ni casi duplicados: la independencia visual aún necesita revisión.
2. Cantidad de **registros** frente a archivos únicos por producto. Registros reutilizados en distintas piezas o productos se marcan como riesgo.
3. Presencia de FK `piece_ref_id`, `device_id` y `boot_id` en SQLite (equivalente al control de sesión de AGROP-39). La unión pieza–sesión–SHA evita separar copias del mismo archivo.
4. Etiquetas con revisión documentada, diversidad de clases y conflictos de etiquetas para una misma imagen/grupo.
5. Puertas estructurales por producto: al menos 3 grupos independientes para entrenar/validar/probar; 2 clases distintas y **3 grupos independientes por clase** para intentar colocar cada clase en las 3 particiones. Son mínimos de **viabilidad de la partición**, no mínimos estadísticos ni umbrales de desempeño.
6. La salida `preparado_para_intentar_particion` **no** significa que el split ya exista ni que el modelo pueda aceptarse: el Incremento 03 deberá comprobar ausencia de fugas, estratificación real, tamaño adecuado, etiquetas y métricas en conjunto de prueba independiente.

## Interpretación de un bloqueo

`bloqueado_por_datos_insuficientes` es un **resultado válido**, no un error de ejecución. Si faltan archivos y manifiestos, se reporta `insumos_no_disponibles`. Si falta el esquema esperado de SQLite o el JSON de anotaciones es inválido, se produce un error explícito y no se reemplazan datos reales por valores inventados.

**Referencia previa (no sustituto de esta ejecución local):** `backend/dataset/salidas/reporte_integridad.json` de AGROP-39 registró 3 fotografías consultadas, 1 elegible, 2 excluidas y 1 grupo independiente; por ello no generó particiones. El informe AGROP-41 documentó 6 registros de vista reutilizando 3 fotografías únicas, con máscaras por confirmar. Ambos son antecedentes históricos, no resultados actualizados de AGROP-42.

## Pruebas

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -v
```

Las pruebas nuevas crean SQLite e imágenes temporales **sintéticas para probar el software**. No representan un dataset real de entrenamiento ni una evaluación de precisión. Guardar la salida de consola y el JSON de la auditoría real como evidencias de Jira.
