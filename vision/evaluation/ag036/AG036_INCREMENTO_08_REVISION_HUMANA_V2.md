# AgroScan — AG-036 / Incremento 08: universo v2 y revisión humana ciega

## Qué entrega

- `construir_universo_v2.py`: lee el inventario **v2 existente**; comprueba ruta, SHA256 e identidad de grupo declarada; genera `universo_AG036_v2.csv`, `grupos_revision.csv` y `resumen_universo.json`. No genera etiquetas.
- Modificación **aditiva** de `preparar_paquetes_revision.py`: conserva `indice.html`, `revision_A.csv`, `revision_B.csv`, ZIP sellados, acta y todos los mecanismos de control del incremento 02. Añade `formulario_A.html` o `formulario_B.html` y 75 previsualizaciones JPEG reducidas a cada ZIP; los 75 originales y sus SHA256 permanecen intactos.
- `formulario_revision_offline.py`: formulario para abrir localmente, visualizar todas las vistas por grupo y escoger E0, E1, E2, no evaluable o pendiente. Requiere justificación, evidencia textual y Rxx + localización para E1/E2. Exporta `AG036_Devolucion_A.zip` o `AG036_Devolucion_B.zip` que incluye `revision_A.csv`/`revision_B.csv` y sus `soportes/` basados en texto **escrito por el revisor**. Incluye guardar/reabrir progreso JSON. No hay conexión de red ni etiquetas preasignadas.

## Alcance aplicado a v2

| Fuente declarada | Grupos de carpeta | Vistas | Preselección | Motivo |
|---|---:|---:|---|---|
| Mango Kent COFiLAB externo | 15 | 30 | sí | piloto exploratorio, **variedad no verificada independientemente** |
| Tomate rojo Hohenheim externo | 15 | 45 | sí | piloto exploratorio, tipo y fuente sujetos a revisión |
| Mango capturado en proyecto | 3 | 8 | no | variedad Kent **no acreditada**; no falsificarla |
| Tomate capturado en proyecto | 2 | 14 | no | algunos grupos contienen múltiples códigos E-*; identidad de pieza no acreditada |
| **Total** | **35** | **97** | **30 grupos, 75 fotos** | |

La preselección **no** demuestra independencia física, identificación botánica o derecho a redistribución; se basa exclusivamente en la estructura declarada por el usuario. Los campos `lote_id` (p. ej. `EXT_COFILAB`) y `sesion_id` (p. ej. `GRP_KENT_EXT_01`) son **identificadores técnicos**, no actas de lote o fechas reales. No usar estas 30 filas como 30 frutos independientes acreditados hasta completar la verificación externa de procedencia y agrupación. La declaración de la carpeta Kent se conserva como `variedad_declarada=Kent` solo por compatibilidad con el auditor; **no constituye certificación**. Las rúbricas `kent-ext-v0.4` y `tomato-ext-v0.2` requieren revisión/aprobación formal antes de una inferencia conclusiva.

**Derechos de uso:** no publicar ni enviar los ZIP con imágenes de COFiLAB/Hohenheim a terceros sin verificar primero licencias y permisos. Es posible inspeccionar la versión local privadamente como piloto técnico, sujeto a las condiciones aplicables.

## PowerShell — desde la raíz del repositorio

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$datos = "$env:USERPROFILE\Documents\AgroScan_AG036_Multifuente_v2"
$base = "$env:USERPROFILE\Documents\AgroScan_AG036_08"

# Un único comando construye los metadatos, sin editar las 97 filas a mano.
& $py -m vision.evaluation.ag036.construir_universo_v2 `
  --inventario (Join-Path $datos 'inventario_multifuente.csv') `
  --raiz-imagenes (Join-Path $datos 'imagenes') `
  --directorio-salida (Join-Path $base 'universo_01')

# Prepara las mismas 30 fichas para dos revisores, cegados uno respecto del otro.
& $py -m vision.evaluation.ag036.preparar_paquetes_revision `
  --universo (Join-Path $base 'universo_01\universo_AG036_v2.csv') `
  --raiz-imagenes (Join-Path $datos 'imagenes') `
  --directorio-salida (Join-Path $base 'entrega_01')
```

Los directorios de salida deben ser **nuevos**. No borrar ni sobrescribir revisiones previas; use `universo_02`/`entrega_02` para una nueva versión.

**Para revisar:** extraer `AG036_Revisor_A.zip` en un directorio exclusivo para A y abrir `formulario_A.html` desde la carpeta extraída. B hace lo mismo con su propio ZIP y `formulario_B.html`. Cada uno introduce **su propio** `revisor_id` y, mirando imágenes y rúbrica, selecciona una decisión, justificación y criterios relevantes. La opción **Pendiente** no crea revisión; **No evaluable** indica que una pieza no puede juzgarse con estas vistas. El botón de exportación crea `AG036_Devolucion_A.zip` o `...B.zip` con `revision_A.csv`/`revision_B.csv` y respaldos de texto escritos por cada revisor.

**Para consolidar:** extraer el ZIP devuelto por A dentro de `(Join-Path $base 'devoluciones\A')`; extraer el ZIP devuelto por B dentro de `devoluciones\B`; no combinarlos.

```powershell
& $py -m vision.evaluation.ag036.consolidar_devoluciones `
  --preparacion (Join-Path $base 'entrega_01') `
  --universo (Join-Path $base 'universo_01\universo_AG036_v2.csv') `
  --raiz-imagenes (Join-Path $datos 'imagenes') `
  --devolucion-a (Join-Path $base 'devoluciones\A') `
  --devolucion-b (Join-Path $base 'devoluciones\B') `
  --directorio-salida (Join-Path $base 'consolidacion_01')
```

El informe calcula cobertura, pares concordantes, discrepancias y kappa cuando haya suficientes pares válidos. No se debe fabricar respuesta humana, fecha, soporte ni revisión para cerrar el ticket. Si hay discrepancias, registrar conciliación humana por separado.

## Pruebas y validaciones realizadas

- `python -m unittest discover -s vision/tests -p 'test_ag036_*.py' -q`: **119 pruebas aprobadas** en entorno local de preparación, incluidas 11 nuevas.
- Inventario v2 real: **97 imágenes, 35 grupos, 30 grupos seleccionados y 75 vistas**, todos los SHA256 verificados.
- Integración con empaquetador real: `AG036_Revisor_A.zip` y `AG036_Revisor_B.zip` preparados; cada uno contiene 30 filas sin etiqueta, 75 fotografías, `formulario_X.html`, `indice.html`, manifiesto, guía y acta de hashes. Ambos archivos pasan `zipfile.testzip()`.
- El JavaScript pasó `node --check`. En una prueba sintética con Chromium/Playwright se introdujeron respuestas en ambos formularios, se descargaron los ZIP de devolución, el auditor leyó sus CSV y soportes y el consolidador aceptó ambas devoluciones. El entorno de navegador de pruebas bloquea la carga de imágenes por URL local; no se afirma prueba visual de fotos en Chromium. Los archivos originales y las previsualizaciones quedaron incluidos y verificados en los ZIP reales.
- **0 etiquetas humanas producidas, 0 revisores verificados, cierre total AG-036 = NO.**

## Publicación en Git

Agregar solo los archivos de código, documento y pruebas. **No subir** imágenes, ZIP sellados, CSV de opiniones personales ni soportes humanos a repositorios públicos.
