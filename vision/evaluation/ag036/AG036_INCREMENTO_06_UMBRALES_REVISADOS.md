# AG-036 — Incremento 06: análisis retrospectivo de umbrales de YOLOE

## Objetivo y alcance

Contrastar los umbrales `0.40`, `0.30` y `0.25` **sin volver a ejecutar YOLOE** y sin modificar el umbral usado en la captura productiva. Se utilizan `resultados_deteccion.csv` de las 97 imágenes v2 y el CSV de 32 veredictos humanos del conjunto seleccionado por rechazo automático.

La ejecución original de YOLOE usó `conf=0.25`; por lo tanto, **no podemos analizar umbrales menores a 0.25** ni recuperar los candidatos descartados durante la inferencia. El análisis solo varía el umbral de captura; no relaja la condición de exactamente **un candidato de clase esperada** y **máscara poligonal presente**.

## Resultados observados del conjunto v2

| Umbral | Candidatos de captura | Aumento vs. 0.40 | Nuevos marcados «Bien localizada» |
|---:|---:|---:|---:|
| 0.40 | 65/97 | 0 | 0 |
| 0.30 | 83/97 | 18 | 18 |
| 0.25 | 86/97 | 21 | 21 |

La revisión identificó **10 fallos** (7 de clase esperada ausente y 3 sin detección); además, **1 imagen** de múltiples candidatos, aunque marcada «Bien localizada», debe seguir bloqueada en captura automática. Los **65 casos listos originalmente no cuentan con revisión humana** en este conjunto. No se deben publicar tasas de exactitud, precisión, sensibilidad ni de falsos positivos a partir de esta selección no aleatoria.

**Decisión:** mantener por ahora el umbral 0.40 en producción. Usar este análisis para planificar un nuevo lote con negativos difíciles, condiciones variadas, verificación de cajas y referencia humana suficiente. No inferir causalidad por la proximidad de la cámara.

## Ejecución en Windows PowerShell desde la raíz del repositorio

Descargar el CSV validado de las **32 revisiones** (entregado junto al parche) a `Descargas`, sin editar SHA256 o rutas. Reutilizar los resultados ya generados en `Documentos`:

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$detector = "$env:USERPROFILE\Documents\AgroScan_AG036_Deteccion_97_v2\resultados_deteccion.csv"
$revisiones = "$env:USERPROFILE\Downloads\AgroScan_AG036_RevisionManual_v2_32.csv"
$salida = "$env:USERPROFILE\Documents\AgroScan_AG036_Umbrales_97_v2"

& $py -m vision.evaluation.ag036.evaluar_umbrales_revisados `
  --resultados $detector `
  --revisiones $revisiones `
  --salida-dir $salida

& $py -m unittest discover -s vision/tests -p 'test_ag036_evaluar_umbrales_revisados.py' -q
& $py -m unittest discover -s vision/tests -p 'test_*.py' -q
```

La carpeta de salida debe **no existir** (no se sobrescriben evidencias). Se generan:

- `resumen_umbrales.json`: totales, recuentos por estado, comprobaciones y SHA256 de entradas.
- `escenarios_97.csv`: una fila por fotografía, decisiones a cada umbral y veredicto de revisor o `SIN_REVISION`.
- `fallos_confirmados.csv`: casos de revisión `YOLOE falló` y `Caja incorrecta`.
- `informe_umbrales.md`: resumen y restricciones metodológicas.

## Siguiente incremento

Antes de calibrar el umbral de producción, evaluar las 65 imágenes originales «listas» y ejemplos negativos / difíciles; confirmar visualmente identidad y cajas. Para el objetivo de calidad E0/E1/E2 (AG-036 / AG-034), asignar etiquetas **por pieza física** mediante dos revisores independientes y rúbricas versionadas. Detección de mango/tomate y calidad E0/E1/E2 no son tareas equivalentes.

**No incluir fotos ni resultados privados en el commit.** Solo scripts, pruebas y documentación. Las fuentes externas requieren revisión de atribución y licencia antes de su redistribución.
