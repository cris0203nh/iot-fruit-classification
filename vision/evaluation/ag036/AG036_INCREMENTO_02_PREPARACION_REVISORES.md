# AgroScan — AG-036 / AGROP-44 — Incremento 02: paquetes independientes

## Alcance

Dos utilidades para **hacer operativa** la evaluación humana independiente, sin fabricar anotaciones:

- `inventariar_fotografias.py`: recorre fotos originales JPG/PNG, verifica decodificación e integridad, extrae ruta relativa y SHA256 y genera `universo.csv` **sin asignar** producto, variedad, lote, pieza, sesión o rúbrica. Por defecto ninguna pieza está seleccionada.
- `preparar_paquetes_revision.py`: consume un `universo.csv` completado y un conjunto de imágenes respaldadas, comprueba los controles **existentes** de `auditar_etiquetado.py`, y produce **dos ZIP diferentes**, uno para A y otro para B, con las mismas vistas pero sin etiquetas del otro revisor. Incluye `indice.html` para consultar las imágenes sin red, `revision_A.csv` o `revision_B.csv` con IDs de pieza y rúbrica **prellenados**, `GUIA_REVISION.md` y manifiesto SHA256; no incorpora etiquetas, nombres de revisores ni fechas ficticias.
- `AG036_acta_preparacion.json`: mantiene hashes de las dos entregas, dataset de origen y lista de piezas efectivamente seleccionadas. No valida por sí sola la procedencia ni la representatividad de las imágenes.

La solución **no sustituye** la revisión humana, la validación de rúbricas `kent-ext-v0.4` / `tomato-ext-v0.2`, la aprobación del tipo de tomate o el cierre de AG-030 y AG-035. La revisión de imágenes de mango Ataulfo no acredita Kent. YOLOE detecta fruta; no emite etiquetas E0/E1/E2.

## Paso 1: disponer de fotografías legítimas

Guarde fotografías reales autorizadas en una **carpeta privada fuera del repositorio**. Debe conocer el origen, variedad/tipo y la identificación de cada fruta para completar el CSV. Los archivos de prueba o datasets externos sin identidad acreditada **no** se convierten por este script en capturas propias. El inventario no presupone permisos de uso.

En PowerShell, desde la raíz del proyecto:

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$trabajo = Join-Path $env:USERPROFILE 'Documents\AgroScan_AG036'
$imagenes = Join-Path $trabajo 'imagenes'
New-Item -ItemType Directory -Force -Path $imagenes | Out-Null
# Ponga AQUÍ las fotografías autorizadas que efectivamente se revisarán.
& $py -m vision.evaluation.ag036.inventariar_fotografias `
  --directorio-imagenes $imagenes `
  --salida-csv (Join-Path $trabajo 'universo.csv')
```

Si la carpeta está vacía devuelve error y **no genera un universo ficticio**.

## Paso 2: completar el universo ANTES de que los revisores vean imágenes

Abra `universo.csv` y complete por cada fotografía los campos reales:

- `producto`: `mango` o `tomate`; `variedad_declarada`: `Kent` **solo cuando se haya acreditado como tal** para mango, o el tipo documentado de tomate.
- `lote_id`, `pieza_id`: identificadores reales y estables; múltiples vistas de la misma fruta llevan el mismo par de IDs y `sesion_id` según el registro de captura.
- `rubrica_version`: versión realmente usada por los revisores. No mezcle versiones diferentes de un mismo producto en una auditoría agregada.
- `seleccion_doble`: cambie a `si` **solo** para las piezas incluidas en el subconjunto elegido previamente; complete `criterio_seleccion` con una razón verificable de selección antes de conocer sus etiquetas. Las no seleccionadas mantienen `no`.
- `imagen_relativa` y `sha256_imagen` se calculan automáticamente; NO cambie los hashes ni reasigne fotos a otra pieza.

Para que el auditor acepte el universo, **también deben completarse los datos de las filas no seleccionadas**, o sacarlas del universo mediante una delimitación documental previa; el registro conserva evidencia de exclusiones. Cada vista debe tener identidad de pieza declarada y su hash real.

## Paso 3: generar y distribuir paquetes independientes

```powershell
& $py -m vision.evaluation.ag036.preparar_paquetes_revision `
  --universo (Join-Path $trabajo 'universo.csv') `
  --raiz-imagenes $imagenes `
  --directorio-salida (Join-Path $trabajo 'entrega_01')
```

Se generarán:

```text
Documents/AgroScan_AG036/entrega_01/
  AG036_Revisor_A.zip
  AG036_Revisor_B.zip
  AG036_acta_preparacion.json
  LEEME_ENTREGA.txt
```

Entregue **solo** `AG036_Revisor_A.zip` al revisor A y **solo** `AG036_Revisor_B.zip` al revisor B. El responsable conserva el acta en su carpeta privada. Cada revisor abre `indice.html` dentro de su ZIP descomprimido y completa su CSV. La evidencia/justificación es manual, no asignada por el sistema. No deben comparar sus respuestas antes de finalizarlas.

Los ZIP contienen las fotografías originales; controle el consentimiento y la privacidad. **No subir a GitHub** ZIP, imágenes, actas con identificadores sensibles o CSV completados sin revisar autorizaciones.

## Paso 4: consolidar revisiones sin sobrescribir originales

Cuando ambos revisores entreguen sus CSV y respaldos, coloque `revision_A.csv`, `revision_B.csv` y los archivos de soporte bajo una carpeta privada. Los nombres de respaldo deben mantenerse únicos al reunir soportes. El auditor existente calcula la cobertura, la matriz de acuerdo y kappa:

```powershell
$soportes = Join-Path $trabajo 'soportes'
New-Item -ItemType Directory -Force -Path $soportes | Out-Null
# Coloque las hojas y soportes REALMENTE recibidos; no genere etiquetas aquí.
& $py -m vision.evaluation.ag036.auditar_etiquetado `
  --universo (Join-Path $trabajo 'universo.csv') `
  --revision-a (Join-Path $trabajo 'revision_A.csv') `
  --revision-b (Join-Path $trabajo 'revision_B.csv') `
  --raiz-imagenes $imagenes `
  --raiz-soportes $soportes `
  --salida (Join-Path $trabajo 'AG036_auditoria_01.json')
```

Si aparecen discrepancias, la persona árbitro registra su conciliación en `conciliaciones.csv` sin cambiar A/B y se ejecuta con `--conciliaciones` y **una ruta nueva** para el informe. El sistema no sobrescribe salidas ni acredita por sí solo que un revisor sea competente.

## Verificación automática

```powershell
& $py -m unittest discover -s vision/tests -p 'test_ag036_*.py' -q
& $py -m unittest discover -s vision/tests -p 'test_*.py' -q
```

Los tests usan **fotografías y etiquetas sintéticas creadas para probar el software**, no resultados reales de AgroScan. La emisión de ZIP exige una selección elegible y un universo consistente. Con fotografías insuficientes o sin identidad verificada, el proceso permanece pendiente.

## Limitaciones explícitas

1. No establece automáticamente `E0/E1/E2` ni acepta equivalencias de `primera/segunda`.
2. No demuestra identidad de variedad, licencia, aprobación de rúbrica, competencia de evaluadores ni representatividad estadística.
3. No modifica archivos existentes de AG-034, AG-035, AG-036, FastAPI o React.
4. No da por terminada AG-036; el cierre exige revisión humana independiente, conciliaciones y evidencias de dependencia AG-030/AG-035.
