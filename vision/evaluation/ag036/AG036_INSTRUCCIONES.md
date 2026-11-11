# AG-036 — Sprint 10: cobertura, calidad y discrepancias de etiquetado

## Propósito y criterio de aceptación

Realizar una auditoría **por lote, pieza y producto** de un subconjunto seleccionado *antes de revisar los resultados*, doblemente etiquetado por dos personas diferentes, con identificación de discrepancias y un informe reproducible. **No se crean etiquetas ni resultados de campo ficticios.**

- **Dependencias de Jira:** AG-030 (muestras de origen) y AG-035 / AGROP-43 (métricas de producto/calidad); verificar sus evidencias y estados antes de cerrar AG-036.
- **Alcance:** mango **Kent** declarado con rúbrica `kent-ext-*` y tomate con `tomato-ext-*`; fotografías de mango Ataulfo no se cuentan como Kent.
- **No equiparar** acuerdo entre revisores con exactitud del clasificador o verdad de campo.
- **Fuente documental contrastada:** AGROP-15 *Criterios Consistentes v0.2* (28/10/2026) define E0 (sin defecto relevante visible), E1 (defecto visible a valorar) y E2 (indicio grave a revisar con prioridad); no equivalen a calificación comercial. AGROP-13 *Mango Kent v0.4* y AGROP-14 *Tomate v0.2* son versiones documentales **pendientes de aprobación externa**.
- **Brecha detectada en repositorio actualizado `2f29568`:** AG-035/AGROP-43 procesa `primera`/`segunda`, mientras AG-034 v14 y AGROP-15 operan con `E0/E1/E2`. **No hay equivalencia documentada ni conversión válida**; se mantienen informes separados. Los pipelines/antecedentes pueden mencionar versiones v0.5 de Kent o v0.1 de tomate. En AG-036 solo se compara un conjunto cuando ambos revisores utilizan la *misma versión por pieza* y todas las piezas seleccionadas de un producto utilizan una única versión. La aprobación debe confirmarse fuera del script.
- La integración posterior con YOLOE detecta/segmenta fruta, **no** produce por sí misma etiquetas E0/E1/E2 verificadas.
- El código verifica presencia, integridad digital y metadatos declarados; **no puede demostrar de modo automático que el revisor sea humano, independiente y competente**, ni que la rúbrica esté aprobada.

## Qué se entrega en este incremento

- `auditar_etiquetado.py`: reporta cobertura por producto, pares completos, pares no evaluables, faltantes, matriz de concordancia, acuerdo observado y **kappa de Cohen no ponderado** cuando sea matemáticamente calculable; lista las discrepancias.
- `plantillas/universo.csv`: **una fila por fotografía/vista** identificada con `lote_id` y `pieza_id`; permite varias vistas de la misma pieza, sin duplicar el denominador.
- `plantillas/revision_A.csv` y `revision_B.csv`: **una fila por lote/pieza seleccionada y por persona**, preparadas de forma independiente. Las plantillas se distribuyen por separado; el revisor B no debe ver las decisiones de A antes de entregar su archivo.
- `plantillas/conciliaciones.csv`: registro **opcional** de discrepancias resueltas por una tercera persona o de propuesta de ajuste de rúbrica; no altera etiquetas originales ni confirma aprobación institucional.
- `vision/tests/test_ag036_concordancia.py`: pruebas sintéticas del software, no evidencia agronómica.

## Protocolo operativo recomendado

1. **AG-030:** formar un listado verificable de frutas reales del alcance piloto (lote, pieza, sesión, foto original y SHA256). Confirmar que hay permisos/licencias para usar los archivos, sus rúbricas y los identificadores de origen.
2. **Preseleccionar el subconjunto doble:** documentar `seleccion_doble=si` y `criterio_seleccion` *antes de conocer las etiquetas*. Cubrir mango Kent/tomate, distintas clases esperadas, casos fronterizos e imágenes no evaluables. No fijar arbitrariamente el tamaño ni seleccionar solo casos fáciles.
3. **Revisores A y B:** cada uno revisa independientemente la misma evidencia y misma versión de la rúbrica, anota estado `pendiente`/`no_evaluable`/`etiquetada`; si etiqueta, el valor es `E0`, `E1` o `E2`; registra fecha con zona horaria, justificación y soporte. Para E1/E2 debe indicar criterio `Rxx` y ubicación de la evidencia (p. ej., vista y región). Peso/calibre del mango y diámetro del tomate son independientes del grado visual. Todos los registros de una misma plantilla deben corresponder a una sola persona.
4. **Auditoría:** ejecutar el comando inferior. Si no hay ningún par etiquetado, `acuerdo_observado` y `kappa_cohen_no_ponderado` deben ser `null` (no cero ni 100%). Para kappa degenerado (una sola categoría constante de ambos revisores), es `null` aunque exista acuerdo.
5. **Conciliación:** solo después de congelar A y B, revisar la lista de casos. Un tercero puede documentar `resuelto`, con decisión y evidencia. Si los criterios son ambiguos, registrar `ajuste_rubrica_propuesto` para aprobación externa; **nunca cambiar retrospectivamente los CSV originales**.
6. **Jira:** adjuntar informe, lista de casos, protocolo de selección, respaldo de la doble revisión y acta/versionado de ajustes. Solo marcar Done cuando se acrediten las revisiones reales, exista evidencia suficiente y se hayan revisado AG-030/AG-035.

## Estructura de carpeta de trabajo local

```text
Documentos/AG036_Revision/
  universo.csv
  revision_A.csv
  revision_B.csv
  conciliaciones.csv           # opcional: usar cuando haya desacuerdos
  imagenes/                  # JPG/PNG originales, no añadir al repositorio público
  soportes/                  # fichas, evidencia de sesión, actas, etc.
  AG036_auditoria_01.json    # salida generada
  AG036_auditoria_01.md      # salida generada
```

Todas las rutas dentro de CSV relativas a `imagenes/` o `soportes/` usan `/` y **no** pueden contener `..`, rutas absolutas ni enlaces simbólicos. Las imágenes pueden incluir varias vistas de la misma pieza. El SHA256 debe corresponder a los bytes reales originales. `variedad_declarada` no es una confirmación botánica independiente.

## Comandos PowerShell desde la raíz del repositorio

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
& $py -m unittest discover -s vision/tests -p 'test_ag036_*.py' -v
& $py -m unittest discover -s vision/tests -p 'test_*.py' -q

$dir = Join-Path $env:USERPROFILE 'Documents\AG036_Revision'
New-Item -ItemType Directory -Force -Path (Join-Path $dir 'imagenes'), (Join-Path $dir 'soportes') | Out-Null
$plantillas = 'vision\evaluation\ag036\plantillas'
foreach ($f in 'universo.csv','revision_A.csv','revision_B.csv','conciliaciones.csv') {
  $destino = Join-Path $dir $f
  if (-not (Test-Path $destino)) { Copy-Item (Join-Path $plantillas $f) $destino }
}

# Cuando existan fotografías, dos revisiones reales y soportes:
& $py -m vision.evaluation.ag036.auditar_etiquetado `
  --universo (Join-Path $dir 'universo.csv') `
  --revision-a (Join-Path $dir 'revision_A.csv') `
  --revision-b (Join-Path $dir 'revision_B.csv') `
  --raiz-imagenes (Join-Path $dir 'imagenes') `
  --raiz-soportes (Join-Path $dir 'soportes') `
  --salida (Join-Path $dir 'AG036_auditoria_01.json')

# Cuando haya conciliaciones, usar --conciliaciones (Join-Path $dir 'conciliaciones.csv')
# y una ruta nueva --salida (Join-Path $dir 'AG036_auditoria_02.json').
```

Al ejecutar los cuatro CSV vacíos, el programa genera un informe correctamente **sin cobertura, sin métricas y sin cierre**. Para auditar datos nuevos, elegir siempre un nombre nuevo de salida; no se sobrescriben informes previos.

## Lectura de métricas

- **Piezas elegibles:** cantidad de piezas únicas del universo en alcance piloto (no cantidad de fotografías).
- **Cobertura de selección:** seleccionadas / elegibles. No implica que el subconjunto sea representativo.
- **Cobertura de doble grado:** pares E0/E1/E2 efectivamente completados / piezas seleccionadas. Los `no_evaluable` y faltantes se cuentan **por separado**. La **cobertura de doble revisión** incluye también pares completos que ambos registraron como no evaluables; no confundir con cobertura de dos grados válidos.
- **Acuerdo observado:** coincidencias exactas / pares con dos grados E0/E1/E2.
- **Kappa de Cohen:** corrige el acuerdo esperado por proporciones marginales; `null` si no hay pares válidos o si el denominador es degenerado. Sin umbrales arbitrarios para declarar éxito.
- **Discrepancias:** diferencias E0/E1/E2 o desacuerdo sobre si la foto es evaluable; casos pendientes y sin revisar no son acuerdos.

**Campo clave:** `(producto, lote_id, pieza_id)`. Dos lotes pueden tener la misma `pieza_id` sin mezclar evaluaciones. El script bloquea combinar versiones de rúbrica distintas dentro de una misma matriz de concordancia por producto.

**Advertencia:** si se descubre cambio de rúbrica, registrar propuesta separada y versionarla con revisión/aprobación humana. No recalcular los resultados antiguos como si se hubiesen obtenido con la rúbrica nueva.
