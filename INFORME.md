# AgroScan · AGROP-42
## Informe de recopilación fotográfica inicial

**Fecha de consulta** 5 de noviembre de 2026  
**Estado** Inventario preliminar. Entrenamiento pendiente de verificación de etiquetas y de independencia de muestras.

| Conjunto | Meta | Fotografías incluidas | Variedad documentada por la fuente | Faltante |
|---|---:|---:|---:|---:|
| Tomate | 15 | 15 | 3 | 0 |
| Mango Kent | 15 | 4 | 4 | 11 |
| Mango de variedad desconocida | — | 0 | 0 | — |
| **Total** | **30** | **19** | **7** | **11** |

### Variedad y revisión pendiente

| Archivos | Evidencia y estado |
|---|---|
| `mango_kent_01.jpg` | Kent identificado por el fotógrafo en una exhibición de frutos en Florida. El rótulo del cultivar aparece en la toma. |
| `mango_kent_02.jpg` | Kent declarado por el autor como *American Kent Mango*, Kurigram, Bangladesh. |
| `mango_kent_03.jpg` | Frutos del árbol original Kent en Coconut Grove, Florida, según la ficha del fotógrafo. Es una toma general con frutos pequeños en el encuadre. |
| `mango_kent_04.jpg` | Kent declarado por TopTropicals.com en la ficha de Flickr. Cuatro frutos enteros sobre un plato. |
| `tomate_01.jpg` a `tomate_03.jpg` | Bambelo, Dulcemiel y Nebula, respectivamente, según las fichas de Wikimedia Commons. |
| `tomate_04.jpg` a `tomate_15.jpg` | Tomates con superficie exterior visible. Cultivar pendiente de verificar. |

La evidencia de variedad corresponde a la documentación de origen. La identidad individual de los frutos, el lote, el dispositivo específico y la sesión siguen sin acreditarse para las 19 fotos. Algunas tomas muestran varios frutos y el conjunto académico de tomate documenta cuatro vistas por fruto sin un mapa de piezas en el archivo distribuido. Los nombres del ZIP identifican archivos. El CSV conserva vacíos `lote_id`, `pieza_id`, `dispositivo_id` y `sesion_id`, y registra `pieza_confirmada=false`.

No se asignaron clases E0/E1/E2, enfermedades, defectos ni madurez. `etiqueta_fuente` queda vacía. Las rutas de procedencia de las fotos académicas se conservan en las atribuciones para identificar el archivo dentro del contenedor de origen. Los nombres de sus carpetas no se trasladaron como anotaciones de AgroScan.

### Procedencia y selección

- **Tomate.** Cuatro fotos de Wikimedia Commons bajo CC0 1.0 y once fotos publicadas bajo CC BY 4.0 por Mputu, Abdel-Mawgood, Shimada y Sayed. Para el segundo grupo se descargó el archivo publicado en Mendeley, se cotejó su SHA‑256 con el de la ficha de descarga y se seleccionaron archivos de una sola de las dos estructuras de clases del archivo, con separación en su numeración dentro de cada clase y revisión visual. [Mendeley Data](https://data.mendeley.com/datasets/x4s2jz55dx/1)
- **Mango Kent.** Tres originales de Wikimedia Commons y un original de Flickr, cada uno con una ficha que identifica Kent y licencia CC BY-SA. Las atribuciones por archivo enlazan la ficha, el binario publicado y la licencia. [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Mango_Kent_Asit_fs8.jpg) · [Flickr](https://www.flickr.com/photos/top-tropicals/54872069311)
- **Cofilab.** Se localizó la ficha archivada y se inspeccionó el archivo académico. El conjunto tiene dos vistas de cada uno de 50 mangos Kent. Tanto la ficha como la documentación interna solicitan reconocimiento de autoría para el uso del material. Se excluyó porque no se verificó un permiso explícito de redistribución y las imágenes ofrecidas son copias de resolución reducida por la fuente. [Ficha archivada de Cofilab](https://web.archive.org/web/20230327040952/http://www.cofilab.com/portfolio/mangoesdb/) · [Artículo que identifica el conjunto](https://pmc.ncbi.nlm.nih.gov/articles/PMC9655355/)
- **Estudio de Motupe.** El artículo describe 400 fotografías de campo y anuncia disponibilidad de los datos por los autores. Se excluyó el ejemplo de dos vistas publicado como panel. [Frontiers in Plant Science](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2026.1943711/full)
- **Otros candidatos.** Se descartaron las fotografías Kent de Flickr con derechos reservados, las imágenes de plantones y las fotografías que mezclan cultivares sin poder usar una toma original exclusiva de Kent. [Ejemplo en Flickr](https://www.flickr.com/photos/3point141/30335999033) · [Ejemplo de cultivares mezclados](https://commons.wikimedia.org/wiki/File:Mango04_4var_Asit.jpg)

### Controles realizados

- Se abrieron y decodificaron los 19 JPEG. Se revisó cada encuadre para descartar montajes, marcas de agua visibles y tomas prácticamente idénticas.
- Se verificaron 19 SHA‑256 únicos. El importador de AGROP‑42 registró cero candidatos cercanos por dHash a su umbral de cinco bits. La similitud visual y las huellas solo ayudan a comparar fotografías. La independencia de frutos sigue pendiente.
- Se cotejaron las rutas relativas, el producto, la evidencia de variedad, el origen, la licencia y el SHA‑256 con las atribuciones. Cada fila apunta a un archivo presente en el ZIP.
- Se conservaron los bytes publicados en 18 fotos. `mango_kent_03.jpg` usa el JPEG principal del original MPO, que también llevaba una miniatura interna. Se retiró el índice del contenedor y la miniatura sin recodificar la toma. La comparación de los píxeles decodificados fue idéntica y el importador aceptó el JPEG resultante.
- Se probó el flujo de importación del parche AGROP‑42 01A sobre los archivos de entrega. Aceptó 19 registros para inventario y auditoría. La importación no verifica etiquetas de calidad ni habilita entrenamiento.

### Carga en AgroScan

Extrae `entrada_fotos` y `carga_fotos.csv` en `vision/experiments/AGROP42`. Conserva las dos subcarpetas de fotos porque el CSV utiliza sus rutas relativas. Desde la raíz del repositorio, ejecuta en PowerShell con el parche 01A aplicado.

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.preparar_dataset `
  --csv vision/experiments/AGROP42/carga_fotos.csv `
  --input-dir vision/experiments/AGROP42/entrada_fotos `
  --output-dir vision/experiments/AGROP42/dataset_fotos_inicial
```

El directorio de salida debe ser nuevo. Las atribuciones detalladas están en `ATRIBUCIONES.md`.
