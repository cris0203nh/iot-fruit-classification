# AGROP-42 [AG-034] — Etapa 01A · Preparación del dataset de Mango Kent y Tomate

**Estado:** infraestructura de importación y procedencia. No es un dataset real completo y no se ha entrenado ningún modelo.

## Decisiones para AgroScan

- **Mango:** el objetivo del piloto es *Kent*, variedad **verificada en la procedencia**. Una fotografía de variedad desconocida o de otro cultivar puede conservarse en inventario, pero no entra en los manifiestos de auditoría para Kent.
- **Tomate:** mantener su propia rúbrica y sus imágenes separadas. Una etiqueta externa `Fresh/Rotten` no se transforma a E0/E1/E2 ni a R03-R09 automáticamente.
- **Capturas originales:** preferir fotografías de piezas físicas independientes, en al menos dos vistas por fruta. Registrar origen, pieza real, lote, equipo y sesión reales; una misma imagen duplicada **no** crea una pieza adicional.
- **Procedencia:** distinguir `captura_propia`, `externo_original`, `aumentada`, `sintetica`. Los dos últimos tipos quedan fuera de la auditoría de entrenamiento. Los externos requieren comprobación de licencia y variedad cuando corresponda.
- **Revisión:** el CSV solo guarda la etiqueta original declarada por la fuente, nunca produce ground truth. E0/E1/E2 exigen revisión humana basada en la rúbrica y evidencia del revisor antes de incorporarse al JSON de anotaciones.
- **Sesión:** `sesion_id` corresponde al identificador REAL de captura/arranque, no a un número creado para conseguir particiones. AGROP-39/42 agrupa piezas de una misma sesión en el mismo grupo; no inventar nuevas sesiones para multiplicar muestras.

## 1. Preparar fotografías

Desde la raíz de `iot-fruit-classification` en PowerShell:

```powershell
New-Item -ItemType Directory -Force .\vision\experiments\AGROP42\entrada_fotos | Out-Null
Copy-Item .\vision\evaluation\agrop42\dataset_fotos.template.csv .\vision\experiments\AGROP42\carga_fotos.csv
notepad .\vision\experiments\AGROP42\carga_fotos.csv
```

Pon las fotos en `entrada_fotos` **sin modificar los originales**. El CSV tiene un encabezado listo para rellenar; añade una fila por **registro de foto**. Para ver/editar fácilmente CSV en Excel, conserva nombres de columna y guárdalo en UTF-8 con comas.

## 2. Rellenar el registro de procedencia

| Columna | Qué registrar |
|---|---|
| `archivo` | Nombre/ruta relativa de la foto dentro de `entrada_fotos`, p. ej. `mango01_frente.jpg` si ese archivo existe |
| `producto` | `mango` o `tomate` |
| `tipo_fuente` | `captura_propia`, `externo_original`, `aumentada` o `sintetica` |
| `fuente_id` | Nombre de capturador/dataset y versión identificable |
| `fuente_url` | URL oficial cuando sea externo; en capturas propias puede quedar vacío |
| `licencia` | Licencia publicada o `propia` si procede; comprobar derechos antes de declarar confirmado |
| `derechos_confirmados` | `true` únicamente con comprobación documental; de lo contrario `false` |
| `evidencia_derechos` | Fuente de licencia o constancia de autoría/permiso; nunca inventarla |
| `lote_id`, `pieza_id` | Identificadores reales; si falta identidad física no inventar piezas |
| `pieza_confirmada` | `true` solo si se acredita qué pieza física corresponde a esa foto |
| `dispositivo_id`, `sesion_id` | Identificadores reales de adquisición; pueden quedar vacíos si no constan |
| `vista` | p. ej. `frontal`, `lateral` o `posterior`; describe la toma, no garantiza cobertura |
| `variedad_declarada` | Mango `Kent` solo si está respaldado, otras variedades con su nombre real |
| `variedad_confirmada` | `true` si existe evidencia de variedad; no se infiere del color o la forma |
| `evidencia_variedad` | Documento/lote/productor que justifica la variedad |
| `etiqueta_fuente` | Clase original externa, por ejemplo `good`/`defect` o `fresh`/`rotten`; **no** es E0/E1/E2 |
| `observaciones` | Evidencia de recolección o dudas pendientes |

**No rellenar `true` por conveniencia.** Estos campos son declaraciones documentales; el script valida la estructura, no comprueba físicamente la variedad ni la autoría.

## 3. Importar a un nuevo paquete local

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.preparar_dataset `
  --csv vision/experiments/AGROP42/carga_fotos.csv `
  --input-dir vision/experiments/AGROP42/entrada_fotos `
  --output-dir vision/experiments/AGROP42/dataset_v1
```

El destino debe ser nuevo; para corregir metadatos usa `dataset_v2`, `dataset_v3`, etc. **No se sobrescribe un dataset ya generado.** No se crean datos a partir de una plantilla vacía: primero se necesitan fotografías originales reales y filas de procedencia.

Genera:

- `dataset_v1/images/`: copia exacta en bytes de cada imagen única SHA256, sin correcciones ni aumentos.
- `dataset_v1/inventory.json`: inventario de fotos, referencias originales, procedencia, tamaño, SHA256 y huella perceptual dHash.
- `dataset_v1/report.json`: registros, duplicados exactos, pares visualmente parecidos **solo para revisión** y excluidos.
- `dataset_v1/manifests/`: contratos de las fotos elegibles compatibles con el auditor del Incremento 01; agrupa fotos de la **misma pieza declarada**.
- `dataset_v1/annotations_to_review.json`: `{ "annotations": [] }` por seguridad; no contiene etiquetas inventadas.

Las imágenes sin permisos comprobados, de variedad Kent no verificada, sintéticas o aumentadas se registran en inventario, pero **no aparecen en los manifiestos de auditoría**. No conviertas un nombre de archivo en evidencia de pieza, variedad o calidad.

## 4. Auditar después de importar

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar `
  --manifests-dir vision/experiments/AGROP42/dataset_v1/manifests `
  --annotations vision/experiments/AGROP42/dataset_v1/annotations_to_review.json `
  --output vision/experiments/AGROP42/auditoria_dataset_v1.json
```

El auditor también lee el **SQLite local** por defecto. Si necesitas evaluar *solo el conjunto nuevo*, especifica `--db` apuntando a un archivo que no exista (lo informará como `no_disponible`), sin alterar la base AgroScan. Para auditar todos los orígenes conjuntamente usa `--manifests-dir vision/experiments`, sabiendo que puede contar intencionalmente registros duplicados entre manifiestos y el SQLite.

Revisa:

```powershell
$r = Get-Content vision/experiments/AGROP42/auditoria_dataset_v1.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.status
$r.por_producto.mango | ConvertTo-Json -Depth 5
$r.por_producto.tomate | ConvertTo-Json -Depth 5
```

**El bloqueo del auditor es normal** hasta disponer de grupos independientes y al menos dos clases con revisión real. El mínimo estructural de tres grupos por clase no acredita un dataset estadísticamente sólido.

## 5. Revisión de etiquetas antes del modelo

Revisar imágenes por pieza y aplicar la rúbrica específica. En `annotations_to_review.json`, añadir entradas únicamente después de inspección documentada; cada etiqueta debe tener SHA256 real, producto, `label`, `review_verified: true`, `reviewer_id`, `reviewed_at` y `rubric_version`. Guardar por separado las observaciones R03–R08 (mango) / R03–R10 (tomate), y las decisiones no evaluables. Si no existe correspondencia justificada entre `good/defect` y E0/E1/E2, **no convertir las clases**.

Antes de entrenar: confirmar independencia de piezas/sesiones, eliminar fugas por duplicados/casi duplicados, revisar la distribución por clase, fijar la partición e identificar el hardware donde se medirá latencia y memoria. No entrenar con imágenes generadas por IA como si fueran fruta real ni calcular métricas de prueba sobre datos de entrenamiento.

## 6. Fuentes públicas investigadas (no descargadas ni importadas)

| Fuente | Datos conocidos | Uso propuesto | Advertencia |
|---|---|---|---|
| MangoesDB — estudio DOI:10.3390/foods11213483 | 100 imágenes Kent, 50 `good` y 50 `defective` | Prioridad como referencia de Kent **si** se obtiene legítimamente | El enlace histórico a COFILAB no se pudo acceder y la licencia de fotos no quedó confirmada; no importarlas todavía |
| Estudio Kent peruano, DOI:10.1016/j.rico.2025.100589 | 603 imágenes de madurez Kent | Solicitar datos a autores para investigación complementaria | El artículo dice "available on request"; su tarea es madurez, no R03–R06 |
| MangoFruitBD v2, DOI:10.17632/bhrz29mkmr.2 | 1.310 imágenes de huerto, clases patológicas externas | Transferencia/experimento **separado**, no parte del dataset Kent | No afirma variedad Kent; licencia CC BY-NC 3.0; split por imagen no acredita independencia de pieza |
| Tomato fruits dataset, DOI:10.17632/x4s2jz55dx.1 | 600 frutos, 4 tomas por fruto; clases binarias/ternarias | Prioridad tomate, tras verificar metadatos de pieza | CC BY 4.0; sus etiquetas no equivalen a rúbrica tomato-ext-v0.1 |
| Tomato_detection, DOI:10.17632/vy5y8p2kdb.1 | 800 originales antes de aumento; 1.600 finales, `Fresh`/`Rotten` | Evaluación preliminar adicional, no mezclar con lote de captura | CC BY 4.0; el conjunto de entrenamiento contiene 1.200 imágenes tras aumento |

Fuentes oficiales: `https://data.mendeley.com/datasets/bhrz29mkmr/2`, `https://data.mendeley.com/datasets/x4s2jz55dx/1`, `https://data.mendeley.com/datasets/vy5y8p2kdb/1`, `https://pmc.ncbi.nlm.nih.gov/articles/PMC9655355/` y `https://www.sciencedirect.com/science/article/pii/S266672072500075X`.

**No se incluye ningún archivo de esos datasets en el parche.** Su descarga, licencia, identidad, procedencia y disponibilidad por pieza deben comprobarse antes de incorporarlos.

## 7. QA, confidencialidad y versionado

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -v
```

`vision/experiments/` está ignorado por Git. No subir fotos, bases SQLite, inventario sensible ni evidencias de personas en un commit accidental. Versionar **solo** script, plantilla CSV vacía, guía y pruebas. Los tests crean imágenes temporales artificiales **únicamente** para verificar la importación y la seguridad de rutas.
