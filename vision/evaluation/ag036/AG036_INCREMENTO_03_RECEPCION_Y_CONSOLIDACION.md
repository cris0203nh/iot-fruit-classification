# AgroScan — AG-036 / AGROP-44 — Incremento 03: recepción y consolidación de revisiones

## Objetivo

Cerrar **el flujo técnico** entre los paquetes ciegos A/B del Incremento 02 y el auditor de concordancia del Incremento 01, sin inferir atributos visuales ni sobrescribir las decisiones de los revisores.

**Esto no cierra AG-036 en Jira**: la autenticidad de las revisiones humanas, la aprobación de las rúbricas, el origen de las fotografías y las dependencias AG-030/AG-035 requieren comprobación externa.

## Módulo incorporado

`vision/evaluation/ag036/consolidar_devoluciones.py`:

1. Verifica los SHA256 de `AG036_Revisor_A.zip`, `AG036_Revisor_B.zip` contra el acta original de preparación.
2. Revalida el universo y cada fotografía original; comprueba que las fotos dentro de ambos ZIP, los datos de pieza y el manifiesto coinciden con la selección previa.
3. Compara las fichas devueltas con las **filas prellenadas y selladas**: no admite añadir/eliminar piezas ni cambiar producto, lote, pieza o rúbrica.
4. Mantiene las filas sin completar como **sin revisión**. Si una fila está parcialmente editada pero es inválida, se rechaza; no se le asigna una etiqueta implícita.
5. Reúne los archivos de soporte bajo carpetas independientes `A/` y `B/`, impidiendo rutas inseguras y colisiones entre revisores. Los archivos devueltos permanecen intactos.
6. Invoca el módulo AG-036 ya existente para validar etiquetas, fechas, soportes y evaluadores, calcular la cobertura, acuerdo observado, kappa cuando corresponda y discrepancias.
7. Emite un acta de recepción con hashes, copias originales de los CSV, CSV normalizados y los informes JSON/Markdown. **Nunca sobrescribe** una salida existente.

### Estructura de la carpeta privada de trabajo

```text
Documents/AgroScan_AG036/
  imagenes/                          # Fotografías originales autorizadas
  universo.csv                       # Inventario previamente completado
  entrega_01/                        # Generada por el Incremento 02
    AG036_Revisor_A.zip
    AG036_Revisor_B.zip
    AG036_acta_preparacion.json
  devoluciones/
    A/
      revision_A.csv                  # Devuelto por el revisor A; no editar por el consolidador
      soportes/
        p1.txt                        # Evidencia elaborada por el revisor A
    B/
      revision_B.csv                  # Devuelto por el revisor B
      soportes/
        p1.txt                        # Puede compartir nombre: se aísla como B/p1.txt
  consolidacion_01/                  # Solo se crea después de validar todas las entradas
    originales/A/revision_A.csv
    originales/B/revision_B.csv
    normalizados/revision_A.csv
    normalizados/revision_B.csv
    soportes/A/...
    soportes/B/...
    AG036_acta_recepcion.json
    AG036_auditoria.json
    AG036_auditoria.md
```

La carpeta de salida está **fuera de Git**. Conserve los ZIP sellados de `entrega_01` y el acta de preparación. El CSV devuelto puede contener un registro con `soporte_relativo` igual a `p1.txt` o `soportes/p1.txt`; el archivo debe existir físicamente en la carpeta `soportes` **del respectivo revisor**. No combine los soportes A/B antes de ejecutar el consolidador.

### Ejecución PowerShell desde la raíz del repositorio

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$trabajo = Join-Path $env:USERPROFILE 'Documents\AgroScan_AG036'

& $py -m vision.evaluation.ag036.consolidar_devoluciones `
  --preparacion (Join-Path $trabajo 'entrega_01') `
  --universo (Join-Path $trabajo 'universo.csv') `
  --raiz-imagenes (Join-Path $trabajo 'imagenes') `
  --devolucion-a (Join-Path $trabajo 'devoluciones\A') `
  --devolucion-b (Join-Path $trabajo 'devoluciones\B') `
  --directorio-salida (Join-Path $trabajo 'consolidacion_01')
```

**Requisitos:** (a) `universo.csv` proviene de las mismas fotos originales y debe mantener su SHA256 desde que se prepararon los paquetes; (b) los dos revisores recibieron los ZIP correspondientes; (c) cada uno devuelve su propio CSV y los soportes, sin leer el del otro. Los ZIP no se vuelven a generar después de realizar las evaluaciones.

Para repetir la consolidación tras recibir datos adicionales, utilice otro directorio, por ejemplo `consolidacion_02`: **no modificar ni sobrescribir `consolidacion_01`**.

### Validación de software

```powershell
& $py -m unittest discover -s vision/tests -p 'test_ag036_*.py' -q
& $py -m unittest discover -s vision/tests -p 'test_*.py' -q
```

Se añadieron 24 pruebas de software sintéticas para cobertura de recepción, integridad de ZIP/imágenes, conservación de CSV, separación de respaldos y bloqueo de entradas alteradas. Tras esta incorporación, el conjunto AG-036 incluye 79 pruebas. Estas pruebas **no son anotaciones humanas de frutas reales**.

## Interpretación y límites

- `AG036_auditoria.json` y `.md` son informes reproducibles. Si no hay pares con dos etiquetas E0/E1/E2, acuerdo y kappa son `null`, **no cero**.
- Revisión humana sin terminar no es caso `E0` ni pieza `no_evaluable`; se reporta como registro pendiente.
- Una coincidencia A/B no demuestra que la etiqueta sea correcta ni que el modelo de visión artificial acierte.
- El acta certifica que **los archivos coinciden con los datos recibidos y la preparación documentada**; no es una firma digital, ni demuestra identidad humana o independencia real. La verificación de procedencia y permisos se efectúa fuera del software.
- La concatenación histórica `primera/segunda` de AG-035 no se convierte a E0/E1/E2.
- Mango Ataulfo de datasets externos no se transforma en Kent por renombrar archivos. Los criterios de tomate requieren confirmar el tipo/variedad piloto.
- Rúbricas `kent-ext-v0.4` y `tomato-ext-v0.2`: versiones de referencia pendientes de validación/aprobación de especialistas. No introducir equivalencias ni declarar aprobación automática.
- Para conciliar desacuerdos, conserve la salida de este incremento como línea base y utilice `auditar_etiquetado.py` con `--conciliaciones` sobre **los CSV normalizados y soportes** de `consolidacion_01`, el universo original, las fotos originales y un nombre nuevo de salida. Las primeras decisiones se preservan.

## Criterios reales de cierre en Jira

Un responsable deberá contrastar la selección del subconjunto, confirmar origen/licencias/variedad, recoger dos revisiones independientes de las mismas piezas, registrar discrepancias y resolución humana, adjuntar las evidencias y verificar las dependencias AG-030/AG-035. Hasta entonces, `cierre_total_AG036_acreditado` permanece `false`.
