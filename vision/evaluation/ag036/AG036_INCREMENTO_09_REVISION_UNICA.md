# AG-036 — Incremento 09: auditoría de una sola revisión humana

## Alcance

El protocolo original AG-036 contemplaba dos revisores humanos independientes. Si existe **un solo revisor**, la implementación permite auditar documentalmente su devolución, pero **no calcula acuerdo observado entre revisores ni kappa**, y no cambia retrospectivamente la aceptación del requerimiento original.

El módulo `auditar_revision_unica.py` valida:

- Integridad SHA256 de todas las imágenes del universo, incluido formato MPO.
- Contenido estructural del ZIP recibido, rutas seguras y soportes, sin duplicados de nombre.
- Concordancia entre el universo previamente seleccionado y las piezas realmente revisadas.
- Identificador único de revisor, fechas ISO con zona horaria, rúbrica por producto y evidencia requerida por etiqueta.
- Cobertura y distribución E0/E1/E2, con avisos de lectura para posibles inconsistencias; **nunca cambia etiquetas**.
- Registro explícito de `kappa_entre_humanos: null`, `acuerdo_entre_humanos: null` y `cierre_del_criterio_original_doble_concordancia: false`.

**Ejemplo real documentado, no datos de entrenamiento:** la devolución del revisor `REV_A1` de 9/11/2026 contiene 30 fichas (15 mango, 15 tomate), etiquetas por pieza E0=25/E1=2/E2=3. El universo v2 original incluye 97 vistas, de las cuales 75 pertenecen a los 30 grupos preseleccionados. Las 15 fichas de tomate corresponden a E0; no hay clases E1/E2 de tomate. En mango hay solamente 2 E1 y 3 E2. Esta distribución **no soporta una evaluación robusta del clasificador E0/E1/E2**, especialmente bajo la partición sin fugas exigida en AG-034.

## Ejecutar en Windows PowerShell desde la raíz del repositorio

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$datos = "$env:USERPROFILE\Documents\AgroScan_AG036_Multifuente_v2"
$base = "$env:USERPROFILE\Documents\AgroScan_AG036_08"
$devolucion = "$env:USERPROFILE\Downloads\AG036_Devolucion_A.zip"

& $py -m vision.evaluation.ag036.auditar_revision_unica `
  --universo (Join-Path $base 'universo_01\universo_AG036_v2.csv') `
  --raiz-imagenes (Join-Path $datos 'imagenes') `
  --devolucion-a $devolucion `
  --directorio-salida (Join-Path $base 'auditoria_revision_unica_01')
```

Se crean `auditoria_revision_unica.json`, `alertas_revision.csv` e `informe_revision_unica.md`. Se impide sobrescribir resultados y guardar evidencia privada dentro de Git. Conservar por separado el ZIP devuelto y las actas originales de preparación si existen.

## Cierre de sprint defendible

- **Cerrado técnicamente:** ingesta del dataset v2, detección exploratoria YOLOE, diagnóstico de fallos y registro humano de 30 grupos con integridad comprobada.
- **Pendiente de aceptación o cambio de alcance:** doble revisión independiente y concordancia/kappa del AG-036 original. No declarar `Done` bajo los criterios anteriores sin aprobación de un cambio de alcance por PO/docente.
- **Pendiente para AG-034/AG-035:** etiquetas E1/E2 suficientes de tomate, grupos independientes por clase, rúbricas aprobadas, procedencia/licencia de datasets externos y predicciones de un clasificador de calidad entrenado.
- La asistencia visual de IA puede generar observaciones, **nunca un revisor B humano simulado**.

## Pruebas

```powershell
& $py -m unittest discover -s vision/tests -p 'test_ag036_auditar_revision_unica.py' -q
& $py -m unittest discover -s vision/tests -p 'test_ag036_*.py' -q
```
