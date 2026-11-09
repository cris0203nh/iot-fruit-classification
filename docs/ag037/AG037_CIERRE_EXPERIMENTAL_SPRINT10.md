# AG-037 / AGROP-45 — Cierre experimental y trazabilidad (Sprint 10)

**Estado de la entrega:** implementación del flujo y validación simulada desarrolladas; auditoría retrospectiva de umbrales reproducible. **No se declara calibración estadística ni validación física.**

## Evidencia de integración

- PR [#65](https://github.com/cris0203nh/iot-fruit-classification/pull/65): `feat(AGROP-45): integrar incertidumbre y revisión humana`, fusionado en `main` (09/11/2026); commit de la característica `64b4c4d`.
- Migración SQLite: `c7e41a03b037` aplicada por el operador el 09/11/2026; backend respondió HTTP 200 para autenticación, salud, lotes y evaluaciones.
- Validación proporcionada por el operador: backend completo **118/118**, frontend **43/43**, compilación Vite correcta, integración simulada **7/7**. Estas son ejecuciones locales reportadas mediante registros de PowerShell, no ejecuciones de GitHub Actions.
- La integración simulada utiliza SQLite temporal y pesajes simulados. **No existió ESP32 físico** en esta etapa.

## Evaluación de umbrales con datos reales

El nuevo script `vision/evaluation/ag037/evaluar_umbrales_cierre.py` toma los mismos CSV usados en AG-036:

- 97 registros YOLOE v2 (38 mango, 59 tomate), todos con SHA256 único.
- 32 revisiones humanas de los 32 casos *rechazados* por la regla 0,40. Se asociaron por SHA256; 22 estaban «Bien localizada», 10 «YOLOE falló».
- Las otras **65 fotografías admitidas inicialmente no fueron evaluadas** por el revisor en el archivo de detección.

Se preservan las reglas de clase esperada, exactamente un candidato y máscara disponible, y solo cambia retrospectivamente la confianza mínima.

| Umbral de captura | Admitidas / 97 | Retenidas | Nuevas admitidas vs. 0,40 | Nuevas revisadas bien localizadas | Fallos revisados admitidos | Admitidas sin revisión humana |
|---|---:|---:|---:|---:|---:|---:|
| 0,40 | 65 | 32 | 0 | 0 | 0 | 65 |
| 0,30 | 83 | 14 | 18 | 18 | 0 | 65 |
| 0,25 | 86 | 11 | 21 | 21 | 0 | 65 |

**Interpretación:** los 10 casos anotados como fallos entre los 32 revisados se retienen en todos los escenarios. No se puede extrapolar una tasa de error global de la aceptación, porque 65 admisiones nunca recibieron veredicto humano. El cambio de 0,40 a 0,30 o 0,25 no está autorizado únicamente por este experimento.

### Muestra y limitaciones

- Unidad de análisis: fotografía; 97 archivos **no equivalen a 97 frutas independientes**.
- La revisión humana es **sesgada por selección**, al incluir únicamente rechazos originales.
- El resultado de «Bien localizada» valida visualmente una localización para ese revisor, no automáticamente cajas/máscaras por IoU ni exactitud.
- No se reportan precisión, recall, F1, tasa de falsas aceptaciones ni intervalos estadísticos con denominadores que no existen.
- YOLOE detecta mango/tomate. No devuelve un grado de calidad E0/E1/E2; la revisión AG-036 de grados es un corpus diferente y no se mezcla con esta validación.
- El piso de inferencia original era `conf=0.25`: este análisis no puede reconstruir predicciones descartadas por YOLOE.
- No existe prueba prospectiva con sensor real ni calibración independiente de umbral.

## Reproducibilidad (PowerShell, raíz del repo)

Tras extraer el kit de cierre en `Downloads\AG037_Cierre_Kit` y aplicar su parche:

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$datos = "$env:USERPROFILE\Downloads\AG037_Cierre_Kit\02_DATOS"
$salida = "$env:USERPROFILE\Documents\AgroScan_AG037_Cierre_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

& $py -m unittest discover -s vision/tests -p 'test_ag037_cierre_umbrales.py' -v
& $py -m vision.evaluation.ag037.evaluar_umbrales_cierre `
  --detecciones (Join-Path $datos 'resultados_deteccion_97_v2.csv') `
  --revisiones (Join-Path $datos 'revision_humana_32.csv') `
  --salida $salida
```

El script verifica unicidad de SHA, integridad de contrato, correspondencia de decisiones con imágenes, coherencia de la regla original 0,40 y no sobrescribe evidencias existentes. Emite `resumen_ag037.json`, `casos_trazables.csv`, `matriz_umbrales.csv` e `informe_ag037.md`.

## Matriz de aceptación AG-037

| Requisito | Evidencia | Estado |
|---|---|---|
| Rechazar admisión automática de detecciones dudosas | Backend `app/uncertainty.py`, tests AGROP-45 | Implementado y probado |
| Enviar casos dudosos a revisión | `pending_review` con endpoint y persistencia | Implementado y probado con simulación |
| Permitir resolución humana, incluyendo `no_evaluable` | API autenticada y React | Implementado y cubierto por pruebas automatizadas |
| Conservar el dictamen original y fotografía | Tabla `vision_assessments`, SHA256, snapshots inmutables | Cubierto por tests |
| Comparar umbrales y fundamentar decisión | Este informe con 97 casos y 32 revisiones | Exploratorio, umbral 0,40 mantenido |
| Validación física con ESP32 | Equipo no disponible | **No realizada** |
| Estimar tasa global de falsas admisiones | Los 65 casos aceptados carecen de revisión | **No estimable** |

**Conclusión metodológica:** la implementación y la prueba simulada son cerrables como entrega de software de AG-037. La calibración experimental global, la prueba prospectiva y el hardware real deben mantenerse como limitaciones visibles, no como logros completados. El cierre administrativo en Jira depende de que el criterio de aceptación permita este alcance y de la validación del responsable.
