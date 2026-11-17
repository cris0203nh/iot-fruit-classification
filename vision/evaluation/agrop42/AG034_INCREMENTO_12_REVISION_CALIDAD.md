# AG-034 — Incremento 12: registro verificable de revisión de calidad externa

## Alcance y resultado

Este incremento **no** presenta la revisión visual de ChatGPT como validación humana ni acredita el cierre total de AG-034. Consolida las 90 vistas en 30 **identificadores declarados por su fuente** (15 mango, 15 tomate) y crea una ficha por identificador, conservando los SHA-256 y tres rutas de fotografía. Los identificadores fuente no acreditan por sí mismos la independencia física o las sesiones de captura.

Las observaciones de IA y las máscaras anteriores son **material de apoyo descriptivo**. Las etiquetas E0/E1/E2 requieren evidencia individual y rúbricas aprobadas. Las fotografías de mango son Ataulfo según la procedencia declarada; no deben usarse para validar la rúbrica Kent. En el conjunto actual, el sistema devuelve `entrenamiento_comercial_autorizado=false`, `AG034_cierre_total_acreditado=false`, y ninguna métrica de calidad.

## Ejecutar en PowerShell desde la raíz del proyecto

```powershell
$python = '.\backend\.venv\Scripts\python.exe'
$zip = "$env:USERPROFILE\Downloads\AgroScan_Dataset_30_Frutos_90_Vistas.zip"
$ia = 'vision\evaluation\agrop42\AG034_revision_visual_90_vistas_IA.csv'
$base = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas"
$fichas = "$base\AG034_fichas_revision_30_ejemplares.csv"
$reporte = "$base\AG034_Revision_Calidad_12_01"

& $python -m vision.evaluation.agrop42.preparar_revision_calidad_ag034 plantilla `
  --zip "$zip" --revision-ia "$ia" --salida "$fichas"

& $python -m vision.evaluation.agrop42.preparar_revision_calidad_ag034 auditar `
  --zip "$zip" --revision-ia "$ia" --csv "$fichas" --salida "$reporte"

& $python -m unittest vision.tests.test_ag034_revision_calidad_incremento12 -v
& $python -m unittest discover -s vision/tests -p "test_*.py" -q
```

Las salidas deben tener **nombres nuevos**. El programa no sobrescribe las fichas ni un reporte previo.

## Cómo interpretar la ficha

**Campos inmutables:** `producto`, `id_ejemplar_fuente`, `vistas_declaradas`, `archivos_vistas`, `sha256_vistas`, `revision_mascaras_ia`, `observaciones_ia`, `variedad_mango_fuente`, `procedencia`. No editarlos: permiten detectar cambios en el dataset o la revisión de IA.

**Campos de revisión:** `estado_revision`, `etiqueta_e0_e1_e2`, `revisor_id`, `fecha_revision_iso` (ejemplo `2026-11-05T18:30:00-05:00`), `rubrica_version`, `justificacion_rubrica`, `observaciones_revisor`, `referencia_soporte_pieza_sesion`, `referencia_soporte_etiqueta`.

Estados: `pendiente`, `revisada_sin_etiqueta`, `no_evaluable`, `etiquetada`.

- `pendiente`: sin etiqueta ni campos de revisión humana.
- `revisada_sin_etiqueta` / `no_evaluable`: requieren revisor, fecha con huso horario y motivo, **no** etiqueta.
- `etiquetada`: exige E0/E1/E2, revisor, fecha con huso horario, rúbrica, justificación y referencias de soporte. **Se contabiliza como declaración documental, no como etiqueta acreditada**. El programa no puede comprobar la autenticidad o suficiencia de esas referencias.

Una anotación firmada o un campo completado no demuestra por sí solo que la fotografía sea de una pieza física distinta, que la sesión sea auténtica ni que la revisión cumpla una rúbrica. Es necesario revisar **los documentos reales** de respaldo antes de usarla para un experimento de calidad.

## Riesgos experimentales y condiciones de cierre

1. **Variación de procedencia:** los mangos vienen de un dataset Ataulfo; la rúbrica Kent no es transferible automáticamente. Se requieren fotos Kent verificadas o una rúbrica específica Ataulfo documentada y aprobada.
2. **Independencia de grupos:** tres vistas de un ID son una unidad indivisible y no equivalen a tres muestras independientes. Debe haber evidencia de pieza y sesión, con particiones que eviten fugas.
3. **Clase comercial:** color, manchas, máscara cromática o clasificación mango/tomate no significan defectos E0/E1/E2. Se necesita validación por persona competente y variedad/rúbrica aplicables.
4. **Comparación en mismas muestras:** cuando existan etiquetas acreditadas por producto, comparar reglas y modelo ligero sobre el **mismo test independiente**. Reportar precisión, recall y casos no evaluables de calidad, sin confundir la exactitud previa de mango/tomate.
5. **Hardware:** identificar dónde ejecutará la inferencia (PC/backend local frente a ESP32/cámara), memoria y CPU disponibles, tiempos reales y presupuesto de latencia; medir en ese objetivo antes de aprobar el despliegue.

La actividad AG-034 permite documentar un **cierre parcial de comparación auxiliar**, pero no marcar una comparación completa de calidad ni validación en hardware objetivo. Para Jira, adjuntar el informe de los Incrementos 11 y 12 y la evidencia de las limitaciones, sin alterar el estado a `Done` si el docente requiere todo el criterio de aceptación.

## Privacidad y repositorio

Conservar los originales y los soportes fuera de Git; no hacer `git add .` sobre el directorio con fotos ni fichas completadas. El parche añade solamente código, pruebas y este documento. No modifica archivos previos, no sobrescribe imágenes y no entrena modelos.

## Verificación criptográfica del informe

Después de generar el informe, ejecutar:

```powershell
& $python -m vision.evaluation.agrop42.preparar_revision_calidad_ag034 verificar `
  --zip "$zip" --revision-ia "$ia" --csv "$fichas" --salida "$reporte"
```

Genera `AG034_manifest_integridad.json` y verifica el SHA-256 del ZIP, el archivo de revisión IA, las fichas y los resultados. Si se modifican las fichas, no alterar el informe antiguo: generar un reporte en una **carpeta nueva**. Esta verificación acredita la **integridad digital**, no la corrección de las etiquetas.
