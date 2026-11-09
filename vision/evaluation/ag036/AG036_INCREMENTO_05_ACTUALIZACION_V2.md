# AG-036 — Actualización de fotografías v2 (inventario e ingesta)

- El archivo `AgroScan_Imagenes_Revisadas_v2.zip` contiene 97 imágenes, 35 grupos de carpeta declarados: 8+14 capturas del proyecto, 30 imágenes de mango Kent externo y 45 imágenes de tomate rojo externo.
- Al cotejar por SHA256 con v1: 51 bytes de imagen idénticos; 46 nuevos/cambiados; 31 presentes en v1 ya no aparecen en v2. NO se mezclan los informes entre conjuntos.
- El importador acepta ambas organizaciones de nombres (v1 y v2). El control de tamaño se uniformó a **24 megapíxeles** entre ingesta, inventario y auditor, suficiente para 6000×3376 de la nueva fuente de tomate. Se conserva límite de **12 MiB por archivo** y validación de integridad. **45 archivos con extensión .JPG son MPO internamente**, con dos cuadros; se conserva el contenedor íntegro y el detector procesa el primer cuadro, sin convertirlo en dos muestras independientes.
- La carpeta `TOM_EXT_XX_Tc_XX` se conserva como grupo declarado; el nombre del conjunto no verifica la independencia física de la muestra ni la autenticidad de la licencia de uso.
- Los grupos del proyecto `Candidato_*` se preservan exactamente como enviados, incluso cuando contienen varios códigos `E-*`. Estos códigos no son etiquetas visuales E0/E1/E2.
- El importador crea `inventario_multifuente.csv`, `grupos_candidatos.csv`, `universo_AG036_borrador.csv` y `resumen_multifuente.json`, sin inventar etiqueta, variedad, responsable, lote ni fechas.
- No ejecutar entrenamiento de clasificación visual sin rúbricas, independencia de grupos y etiquetas humanas documentadas; YOLOE solo mide detección exploratoria.

## Windows PowerShell (raíz del repositorio)

```powershell
$py = ".\backend\.venv\Scripts\python.exe"
$zip = "$env:USERPROFILE\Downloads\AgroScan_Imagenes_Revisadas_v2.zip"
$trabajo = "$env:USERPROFILE\Documents\AgroScan_AG036_Multifuente_v2"
& $py -m vision.evaluation.ag036.ingestar_dataset_multifuente --zip $zip --salida-dir $trabajo
& $py -m vision.evaluation.ag036.evaluar_detector_multifuente `
  --inventario (Join-Path $trabajo "inventario_multifuente.csv") `
  --raiz-imagenes (Join-Path $trabajo "imagenes") `
  --salida-dir "$env:USERPROFILE\Documents\AgroScan_AG036_Deteccion_97_v2"
```

Los directorios de salida deben ser nuevos: no se sobrescriben evidencias anteriores. Los resultados de YOLOE v1 pueden conservarse como históricos para 51 imágenes idénticas por SHA, pero una evaluación completa de v2 debe ejecutar las 97 inferencias bajo un solo protocolo.

## Pruebas

```powershell
& $py -m unittest discover -s vision/tests -p "test_ag036_ingesta*.py" -q
& $py -m unittest discover -s vision/tests -p "test_ag036_*.py" -q
```
