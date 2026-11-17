# AgroScan · AGROP-42 — Incremento 07: integración controlada de fuentes externas

## 1. Objeto

Incorporar el paquete `AgroScan_Dataset_30_Frutos_90_Vistas.zip` al circuito documental de AGROP-42 de forma reproducible, sin confundirlo con las **capturas propias** del Incremento 06. El archivo suministrado incluye `trazabilidad.csv`, `LEEME.md`, 45 fotos de mango y 45 de tomate. Las 90 fotografías están agrupadas en **30 identificadores de ejemplar declarados**, con **tres vistas por identificador**.

**Resultado verificado del paquete suministrado**:

- 90 archivos JPEG correctamente decodificados, con SHA-256 y resolución coincidentes con `trazabilidad.csv`.
- 90 SHA-256 distintos: sin duplicados byte a byte.
- 15 identificadores de mango; 15 de tomate; 3 fotografías en cada uno.
- 24 fotografías con alguna dimensión inferior a 224 px; **12 son 100×100 px**, todos los mangos son 1200×1200 px.
- Ninguna fotografía del paquete presenta campos EXIF; no se pueden reconstruir a partir de ellas fecha, dispositivo o sesión física.
- Los mangos corresponden a **Ataulfo**, no al alcance Kent de la rúbrica AGROP-13. Las etiquetas de madurez declaradas por la fuente **no se convierten** a E0/E1/E2.
- Los tomates provienen de diferentes categorías de Fruits-360. El nombre de categoría tampoco equivale a etiqueta de calidad externa o daño.

**Comprobado**: contenido bytes, integridad SHA-256, estructura de directorios, formato JPEG, dimensiones e identificadores declarados coherentes. **No comprobado**: identidad física independiente, número real de sesiones, licencia de cada archivo según versión exacta, cobertura suficiente de toda la superficie, etiquetado de calidad ni autenticidad del proceso de captura.

## 2. Archivos nuevos

- `vision/evaluation/agrop42/ingestar_fuentes_externas.py`: CLI `validar`, `importar` y `verificar`.
- `vision/tests/test_agrop42_fuentes_externas_incremento07.py`: 18 tests nuevos (sin descargar imágenes ni tocar DB).
- Este documento.

El importador verifica ZIP-slip/rutas relativas, SHA, archivos duplicados, imágenes JPEG corruptas, correspondencia de resolución, conflictos de grupo y CSV potencialmente ejecutable, y **nunca sobrescribe una salida existente**.

## 3. Aplicar en Windows (PowerShell)

Desde la raíz de `iot-fruit-classification`, con el Incremento 05 ya aplicado:

```powershell
$patch = "$env:USERPROFILE\Downloads\AgroScan_AGROP42_Incremento07_Fuentes_Externas.patch"
git apply --check $patch
git apply $patch

.\backend\.venv\Scripts\python.exe -m unittest vision.tests.test_agrop42_fuentes_externas_incremento07 -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q
```

Coloca el ZIP de fotografías en `Descargas`; si ya se encuentra en otra ubicación, ajusta `$zip`:

```powershell
$zip = "$env:USERPROFILE\Downloads\AgroScan_Dataset_30_Frutos_90_Vistas.zip"
$base = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas"
$salida = "$base\ingesta_001"
New-Item -ItemType Directory -Force "$base" | Out-Null

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.ingestar_fuentes_externas validar --zip "$zip"
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.ingestar_fuentes_externas importar --zip "$zip" --salida "$salida"
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.ingestar_fuentes_externas verificar --salida "$salida"
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar_revisiones `
  --csv "$salida\revisiones_pendientes.csv" `
  --output "$salida\auditoria.json"
```

**No** procesar este ZIP como `captura_propia` con `registrar_capturas.py` del Incremento 06: son fuentes de terceros.

## 4. Salida (fuera del repositorio)

```text
ingesta_001/
  originales/<SHA256>.jpg          # JPEG exactos del ZIP (mismas huellas)
  inventario_externo.csv          # 90 filas con procedencia y agrupación DECLARADAS
  revisiones_pendientes.csv       # 90 filas; ninguna etiqueta E0/E1/E2
  control_externo.json            # SHA del ZIP/inventario y verificación técnica
  ATRIBUCIONES.md                # fuente, licencias declaradas y transformaciones
```

`control_externo.json` guarda el SHA-256 de cada foto, del inventario y de la plantilla de revisión; `verificar` detecta modificaciones a esas salidas. Para editar revisiones, **crear una copia versionada** y conservar el original de la ingesta.

La auditoría AGROP-42 recibe 45 filas de mango y 45 de tomate en estado `pendiente`. Debe devolver:

- 0 notas revisadas acreditadas, 0 clases E0/E1/E2, 0 grupos independientes **acreditados**.
- Estado global `bloqueado_por_datos_insuficientes`.
- Ningún entrenamiento, predicción ni métricas reportadas.

La fuente describe agrupaciones de vistas de un mismo fruto, pero no incorpora evidencia individual verificable de sesión, fecha y captura con la cadena de custodia del piloto. Agrupar por nombre ayuda a **evitar fugas de datos**, pero no sustituye comprobar sesiones independientes. Si una pieza aparece en dos archivos, las 3 vistas deben quedar juntas en cualquier futura partición. Las imágenes del mismo video o sesión no deben separarse entre entrenamiento y prueba.

## 5. Uso permitido para continuar el software

Se pueden ejecutar pruebas de: lectura/decodificación, máscaras propuestas, segmentación RGB, descriptores de color, persistencia del inventario, visualización de vistas y tiempos de ejecución (con entorno y hardware documentados). **No** inferir ausencia de defectos de una cara no visible ni reportar exactitud de clases de daño con las etiquetas originales de madurez/variedad.

Para cerrar la **clasificación Kent** y la calidad externa **E0/E1/E2**, hacen falta fotografías de Kent identificados y revisiones con rúbrica correspondiente, variedad corroborada cuando sea parte del requisito, calidad/cobertura suficientes, trazabilidad real de pieza y sesión y anotaciones justificadas por revisor. Es posible aprovechar este paquete como banco técnico experimental separado mientras se consiguen esas evidencias.

## 6. Licencias y publicación

- Mango: fuente y licencia CC BY 4.0 declaradas en el CSV y README; los archivos de mango fueron **reexportados y redimensionados** respecto de sus fuentes, por lo que hay cambios que se deben atribuir.
- Tomate: Fruits-360 CC BY-SA 4.0; las condiciones de compartir adaptaciones deben respetarse si se redistribuyen.
- Las políticas de uso del piloto y la compatibilidad del conjunto mezclado deben revisarse antes de publicar los originales o cualquier derivado. `ATRIBUCIONES.md` incluye detalles.

Mantén fuera de Git: ZIP original, imágenes, inventarios con datos externos, resultados de importación y capturas. Antes de confirmar código, ejecutar `git diff --cached --check` sobre archivos seleccionados y evitar `git add .`.

## 7. Pruebas de este incremento

**18/18** nuevas pruebas aprobadas en entorno local aislado, y **63/63** pruebas de las suites empaquetadas de incrementos 04–07. La suite completa del proyecto (incluidos componentes anteriores no incluidos en esos ZIP) debe reejecutarse en la copia Windows del usuario. No se editaron ni pushearon archivos remotos en GitHub/Jira.
