# AG-034 — Incremento 11: consolidación experimental y trazabilidad

## Propósito y alcance

Consolidar los resultados de los Incrementos 08, 09 y 10 **sin reejecutar entrenamientos** ni inventar etiquetas. El módulo verifica que las evidencias se refieren a las mismas fotografías, que sus huellas SHA-256 concuerdan, que las matrices de confusión corresponden a las predicciones declaradas y que ambos perfiles usan la misma partición de prueba.

**Estado esperado:** `cierre_parcial_documentado`. La clasificación comercial E0/E1/E2, la independencia física de las piezas, la adquisición con cámara AgroScan, la condición Kent y el rendimiento del hardware final **no** están acreditados.

## Archivos nuevos del incremento

- `vision/evaluation/agrop42/consolidar_ag034.py`: CLI `consolidar` y `verificar`, solo biblioteca estándar de Python.
- `vision/tests/test_ag034_consolidacion_incremento11.py`: pruebas de coherencia, integridad, ausencia de fugas de vistas, no sobrescritura y rechazo de certificaciones indebidas.
- Este documento.

No modifica `benchmark_producto_ag034.py`, `perfil_recursos_ag034.py`, los pipelines RGB ni las fuentes fotográficas. No instala dependencias.

## Estructura de evidencias de entrada

Coloca **estos cinco archivos** bajo un directorio de trabajo privado fuera del repositorio:

```text
AG034_Evidencias_11/
  incremento08/
    resultados_por_vista.csv
    informe_tecnico.json
  incremento09/
    AG034_revision_visual_90_vistas_IA.csv
    AG034_benchmark_auxiliar.json
  incremento10/
    AG034_perfil_recursos.json
```

`AG034_revision_visual_90_vistas_IA.csv` se entrega con su autoría y naturaleza de revisión asistida por IA, no como validación humana. El archivo `AG034_benchmark_auxiliar.json` puede reemplazarse por el `AG034_benchmark_final.json` reproducido en Windows, **conservando el nombre de destino de la estructura**. El perfil `AG034_perfil_recursos.json` debe ser la salida de tu propia ejecución en Windows para que el informe consigne ese entorno; no uses las métricas Linux como si fueran mediciones de tu PC.

La carpeta de salida **debe ser nueva**; no se sobrescribe.

### Ejemplo PowerShell (desde raíz del repositorio)

```powershell
$base = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas"
$evi = "$base\AG034_Evidencias_11"
$zip = "$env:USERPROFILE\Downloads\AgroScan_Dataset_30_Frutos_90_Vistas.zip"

# Primero descomprime AgroScan_AG034_Incremento11_Insumos_08_09.zip en $evi.
New-Item -ItemType Directory -Force "$evi\incremento10" | Out-Null
Copy-Item "$base\AG034_benchmark_final.json" "$evi\incremento09\AG034_benchmark_auxiliar.json" -Force
Copy-Item "$base\AG034_Recursos_10_01\AG034_perfil_recursos.json" "$evi\incremento10\AG034_perfil_recursos.json"

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.consolidar_ag034 consolidar `
  --evidencias "$evi" `
  --zip "$zip" `
  --salida "$base\AG034_Consolidacion_11_01"

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.consolidar_ag034 verificar `
  --salida "$base\AG034_Consolidacion_11_01" `
  --zip "$zip"
```

Si tienes tus propios informes locales del Incremento 08, puedes copiar `resultados_por_vista.csv` e `informe_tecnico.json` desde `analisis_rgb_08` hacia `AG034_Evidencias_11/incremento08/` antes de ejecutar; la comprobación de huellas detectará cualquier discrepancia con el dataset.

## Salidas

```text
AG034_Consolidacion_11_01/
  AG034_resumen_consolidado.json
  AG034_informe_para_Jira.md
  AG034_matriz_evidencias.csv
  AG034_manifest_integridad.json
  fuentes/                         # copia de las cinco evidencias originales
    incremento08/...
    incremento09/...
    incremento10/...
```

El ZIP con fotografías **no** se copia dentro del paquete de salida; solo se registra su SHA-256, cotejado con el perfil y con las imágenes declaradas. `verificar` comprueba el manifiesto y, cuando se pasa `--zip`, el dataset original.

Las huellas SHA-256 son un control de integridad y trazabilidad: **no constituyen firma digital, acta de aprobación ni prueba de autoría del operador**.

## Criterios AG-034 verificados y pendientes

| Condición | Situación tras Incremento 11 |
|---|---|
| Comparación reglas frente a regresión logística con mismo test | Cumplida para identificar mango frente a tomate |
| Matrices de confusión consistentes con predicciones | Comprobación automática implementada |
| Trazabilidad ZIP → resultado RGB → revisión IA → benchmark → perfil | Comprobación automática implementada |
| Mediciones de CPU y asignaciones Python | Disponibles del equipo que ejecuta el perfil |
| Selección y justificación del enfoque | Provisional: reglas para el ensayo auxiliar, menor inferencia/JSON |
| Etiquetas externas E0/E1/E2 confirmadas y comparación de defectos | Pendiente |
| Evaluación contra máscara patrón de un operador | Pendiente |
| Medición en hardware objetivo y límites de despliegue | Pendiente |
| Aceptación formal para cierre total de AG-034 | Pendiente |

La métrica de exactitud del ensayo auxiliar no debe presentarse como exactitud agronómica. Los mangos de este dataset son Ataulfo según la fuente: **no** validan la rúbrica Kent.

## Pruebas

```powershell
.\backend\.venv\Scripts\python.exe -m unittest vision.tests.test_ag034_consolidacion_incremento11 -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q
```

Las muestras generadas dentro de las pruebas son **datos sintéticos usados solo para verificar contratos**, no nuevos datos experimentales ni imágenes de frutas reales.

## Evidencia que puede incorporarse a Jira

Adjuntar `AG034_informe_para_Jira.md`, `AG034_matriz_evidencias.csv`, `AG034_resumen_consolidado.json`, `AG034_manifest_integridad.json` y una captura de la ejecución de `consolidar`/`verificar` en Windows. Conservar externamente el ZIP fuente y los CSV originales.

Registrar como avance técnico de AG-034; **no** cambiar el estado a completado como clasificación de defectos mientras los criterios pendientes continúen sin resolver.
