# AgroScan · AGROP-42 · Incremento 06: capturas propias y trazabilidad

## Alcance implementado

Se incorporó una **ingesta reproducible, local, no destructiva y sin entrenamiento** de fotografías tomadas por el equipo a frutas físicas. El módulo `vision/evaluation/agrop42/registrar_capturas.py`:

1. Genera un CSV de ingreso con identificadores de lote, pieza, sesión, operador, cámara, instante de captura con zona horaria, vista, ruta original, procedencia, referencia de autorización y referencias de identidad.
2. Prevalida en lote el CSV y los bytes reales: rutas relativas seguras, JPEG/PNG decodificables, tamaño y dimensión, SHA-256 real, fotos duplicadas, misma pieza en varios lotes, conflictos de operador/dispositivo en una sesión y vistas repetidas de una pieza.
3. Importa **únicamente capturas declaradas como propias** a una carpeta nueva. No modifica el archivo original. Si falla una fila, no produce una importación parcial. Conserva copia con nombre basado en SHA-256.
4. Produce un inventario técnico, un control JSON, un CSV de revisión pendiente compatible con el auditor de AGROP-42 (Incrementos 04/05) y las copias originales. Verifica que los SHA-256 de las copias coincidan con los de origen.
5. Ofrece un subcomando `verificar` para volver a verificar las copias y la integridad del inventario. No valida credenciales de las personas ni autentica una firma digital.
6. Calcula **luminosidad y respuesta de bordes indicativas** en miniaturas, y marca resoluciones reducidas como aviso. No son pruebas de enfoque, color correcto, calidad agronómica ni clases.

**No se han tomado nuevas fotografías ni probado la cámara real en este incremento.** Se han implementado y probado los mecanismos de ingreso con imágenes de prueba generadas dentro de la suite. La identidad de la pieza, variedad, autorización efectiva, sesión, cobertura, foco aceptable y etiqueta E0/E1/E2 requieren comprobación humana y/o documental.

## Preparación física propuesta

- Separar mango y tomate; asignar un `lote_id` identificable. Para mango, declarar la variedad y conservar cómo se comprobará después; **declarar Kent no demuestra que sea Kent**.
- Etiquetar individualmente una sola fruta con `pieza_id` estable. Conservar una foto o una bitácora de esa identidad fuera del campo de visión comercial; no confundir una fotografía con varios frutos con varias piezas verificadas.
- Registrar `sesion_id`, `dispositivo_id`, `operador_id`, fecha y hora reales con zona horaria. Cambiar de sesión cuando cambien las condiciones de captura de manera relevante y documentar la nueva sesión.
- Capturar vistas de cada pieza (por ejemplo, frontal, posterior y laterales), con iluminación difusa, fondo controlado, enfoque y cobertura revisables. Las vistas recomendadas son una propuesta para el piloto, **no un protocolo de aceptación ya validado**.
- Mantener los archivos JPG/PNG originales. No recortar, mejorar, rotar o regenerar los originales antes de la importación. Si se requieren imágenes procesadas, conservarlas como derivados por separado.
- Obtener la autorización aplicable y registrar su referencia. Evitar rostros, personas, etiquetas con datos privados o información sensible. Los JPEG originales pueden conservar EXIF, incluida geolocalización: **no subir la carpeta de ingesta a GitHub ni compartirla públicamente**.

## CSV de ingreso

Ubicación del ejemplo sin registros: `vision/evaluation/agrop42/capturas_propias.template.csv`. Crear un CSV real independiente: un renglón por **fotografía/vista**, reutilizando `lote_id` y `pieza_id` cuando corresponda a la misma fruta. El `registro_id` identifica la vista; no equivale al `pieza_id`.

| Campo | Qué registrar |
|---|---|
| `registro_id` | Identificador único de la fotografía/vista, p. ej. `CAP-20261106-0001` |
| `producto` | `mango` o `tomate` |
| `variedad_declarada` | Variedad manifestada por responsable; obligatoria para mango, pero no queda validada |
| `lote_id`, `pieza_id` | Identificadores físicos estables; no reutilizar `pieza_id` en distintos lotes del mismo producto |
| `sesion_id`, `dispositivo_id`, `operador_id` | Identidad de la sesión, cámara y persona que tomó la foto |
| `capturado_en` | Fecha y hora ISO 8601 **con zona**: `2026-11-06T09:25:00-05:00` (ejemplo de formato, no dato observado) |
| `vista` | `frontal`, `posterior`, `lateral_izquierda`, `lateral_derecha`, `superior`, `inferior`, `oblicua` u `otra` |
| `archivo_relativo` | Ruta relativa a `--entrada` con `/`, p. ej. `lote01/pieza01/frontal.jpg` |
| `procedencia` | `captura_propia`; archivos externos van al inventario externo, no aquí |
| `autorizacion_ref` | Referencia **real** a la autorización o a la fuente de derecho de uso |
| `referencia_identidad_pieza` | Ubicación/ID del respaldo físico de identidad de pieza: ficha, precinto, bitácora, etc. |
| `referencia_identidad_sesion` | ID o ubicación del registro de sesión de captura |
| `observaciones` | Incidencias, iluminación, oclusiones, condiciones y recapturas, sin datos personales innecesarios |

Campos no vacíos **son declaraciones de quien llena el CSV**, no una verificación independiente. La aplicación no agrega `pieza_confirmada=true`, `sesion_confirmada=true`, `calidad_confirmada=true` ni una etiqueta automáticamente.

## Ejecución en PowerShell (desde la raíz de `iot-fruit-classification`)

Crear una carpeta **privada fuera del repositorio**:

```powershell
$base = "$env:USERPROFILE\Documents\AgroScan_Capturas_Propias"
New-Item -ItemType Directory -Force "$base\originales" | Out-Null

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.registrar_capturas plantilla `
  --csv "$base\capturas.csv"
```

Guardar tus fotos propias dentro de `$base\originales` y completar `$base\capturas.csv` con **datos observados**. El CSV de plantilla contiene únicamente encabezados; no hay ejemplos inventados que puedan confundirse con mediciones.

Prevalidar, importar y verificar:

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.registrar_capturas prevalidar `
  --csv "$base\capturas.csv" --entrada "$base\originales"

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.registrar_capturas importar `
  --csv "$base\capturas.csv" --entrada "$base\originales" `
  --salida "$base\ingesta_001"

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.registrar_capturas verificar `
  --salida "$base\ingesta_001"
```

Cada importación exige una carpeta de salida **nueva** (`ingesta_001`, `ingesta_002`, etc.). Nunca sobrescribe un lote previo. Debe estar fuera de `--entrada`. Para una nueva sesión o corrección del CSV, generar nueva ingesta y documentar la versión; no editar los originales en su sitio.

Auditar el CSV pendiente integrado con el Incremento 05:

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar_revisiones `
  --csv "$base\ingesta_001\revisiones_pendientes.csv" `
  --output "$base\ingesta_001\auditoria_revisiones.json"
```

El resultado **esperado es `bloqueado_por_datos_insuficientes`**: hay capturas sin revisión humana. Aunque el informe liste fotografías, las etiquetas elegibles y los grupos acreditados deben permanecer en cero.

## Salida de cada ingesta

```
ingesta_001/
  originales/<sha256>.jpg o .png   # copias exactas; puede conservar EXIF
  inventario_capturas.csv         # metadatos declarados y mediciones técnicas
  revisiones_pendientes.csv       # compatible con el auditor; SIN etiquetas
  control_ingesta.json            # manifiesto de integridad y alcance
```

`control_ingesta.json` y `inventario_capturas.csv` no constituyen por sí solos una firma ni una cadena de custodia inviolable: alguien con permisos puede sustituir ambos. Conservar una copia fechada de la bitácora y, si hace falta trazabilidad robusta, anclar el hash del control en un sistema externo inmutable y con acceso controlado.

## Criterios para pasar a la revisión humana

- Capturas originales disponibles, verificadas por SHA y decodificables.
- Registro de pieza/lote/sesión/dispositivo/operador con fecha y zona horaria.
- Evidencia documental de la identidad de cada pieza y sesión inspeccionada, **no solo texto declarativo**.
- Revisión visual de foco, iluminación, caras no visibles, oclusiones y correspondencia a una única fruta.
- Revisión de licencias/autorización y de variedad (en particular Kent).
- Anotación por revisor identificado, rúbrica versionada, criterio/justificación y corrección de discrepancias.

Solo entonces se pueden completar los campos de revisión en **una copia versionada** de `revisiones_pendientes.csv`. Nunca completar esos valores desde un algoritmo sin revisión acreditada. El diseño del experimento y las particiones se auditan posteriormente, manteniendo todas las vistas de una misma pieza o sesión en un grupo indivisible. No reportar aún entrenamiento ni precisión.

## Pruebas y protección del repositorio

```powershell
.\backend\.venv\Scripts\python.exe -m unittest vision.tests.test_agrop42_capturas_incremento06 -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q

git diff --check
git status --short
```

Agregar a Git **solo** los nuevos archivos de código, prueba, documentación y CSV de plantilla; no agregar `entrada_fotos/`, `capturas.csv` con datos reales, carpetas `ingesta_*`, imágenes, `.env`, bases locales ni documentos personales. Si el patch se aplica sobre archivos previos sin seguimiento, hacer revisión explícita de `git diff --cached --stat` y `git diff --cached --check` antes de confirmar.

## Pruebas locales del autor del parche

El Incremento 06 trae 24 casos automáticos, realizados con archivos sintéticos de prueba generados dentro de carpetas temporales. No constituyen capturas de frutas reales, validación metrológica ni prueba de campo.
