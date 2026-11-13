# AG-055: evaluación exploratoria de 40 fotografías — AGROP-67

Evaluación ejecutada con las etiquetas humanas atribuidas por declaración explícita del usuario a **Junior Pérez, 13/11/2026**. Resultado exploratorio por fotografía; **no constituye validación independiente acreditada ni autoriza cerrar AGROP-67**. No se entrenó, calibró ni ajustó ningún modelo o umbral.

## Entrada y trazabilidad

El CSV recibido contiene 40 filas únicas, 20 mango y 20 tomate, todas etiquetadas E0/E1/E2 y con justificación. Se cotejaron F001–F040, producto y SHA-256 contra el mapa del paquete ciego, sin depender del orden del CSV. No hubo exclusiones. Se conservaron los bytes originales en una copia privada. El CSV se trató exclusivamente como datos.

Los campos de revisor y fecha del CSV están vacíos: la atribución y el día se registran por separado en `report.json`, con fuente `explicit_user_declaration` y precisión de día. No se inventó hora, zona horaria ni firma. También están vacíos los 40 registros de rúbrica, Rxx, ubicación de evidencia visible, exposición previa, soporte y duración. Las justificaciones se preservaron sin editar. No se acredita cegamiento efectivo ni autenticidad mediante software.

SHA-256 del CSV: `812ea007a2ef72895f7d630eaaa5968adc84b1f30582b823248e3c8844373068`.

## Modelos congelados

Inferencia JSON del piloto SVC RBF, versión `ag055-pilot117-svc-rbf-v1`, descriptor `pilot117-global-676-opencv-v1`. Se ejecutó el modelo correspondiente a cada producto; las puntuaciones se conservan sin calibrar. Los modelos exploratorios anteriores utilizan categorías originales incompatibles con E0/E1/E2: no se inventó una conversión entre esas etiquetas.

| Modelo | SHA-256 |
|---|---|
| ag055_pilot117_mango.json | `bac0f0838bb4746cbfc7ae1613160267f7a2bdbbfc3b9ab007cd6c4367566bb4` |
| ag055_pilot117_tomate.json | `54026780117a3006c7f2c0e5e4d5c02d808bfbb01682c1f55b90ed2d74c5d2e9` |

## Resultados realmente medidos

Accuracy y métricas calculadas sobre las etiquetas humanas recibidas. F1 macro es la media no ponderada de E0/E1/E2; precisión, recall y F1 con denominador cero se registran como cero. No se agrupan frutas físicas ni se estima precisión poblacional.

| Producto | n | Aciertos | Accuracy | Precisión macro | Recall macro | F1 macro |
|---|---:|---:|---:|---:|---:|---:|
| mango | 20 | 7 | 0.3500 | 0.1795 | 0.2121 | 0.1944 |
| tomate | 20 | 9 | 0.4500 | 0.5000 | 0.3037 | 0.2718 |

### Mango: matriz de confusión

Filas: etiqueta humana. Columnas: predicción del modelo.

| Humana / Predicción | E0 | E1 | E2 |
|---|---:|---:|---:|
| E0 | 0 | 5 | 3 |
| E1 | 2 | 7 | 2 |
| E2 | 0 | 1 | 0 |

| Clase | n humano | Precisión | Recall | F1 |
|---|---:|---:|---:|---:|
| E0 | 8 | 0.0000 | 0.0000 | 0.0000 |
| E1 | 11 | 0.5385 | 0.6364 | 0.5833 |
| E2 | 1 | 0.0000 | 0.0000 | 0.0000 |

Errores por identificador ciego: F008, F010, F018, F019, F021, F022, F023, F028, F032, F034, F036, F037, F039.

### Tomate: matriz de confusión

Filas: etiqueta humana. Columnas: predicción del modelo.

| Humana / Predicción | E0 | E1 | E2 |
|---|---:|---:|---:|
| E0 | 1 | 1 | 7 |
| E1 | 0 | 0 | 1 |
| E2 | 0 | 2 | 8 |

| Clase | n humano | Precisión | Recall | F1 |
|---|---:|---:|---:|---:|
| E0 | 9 | 1.0000 | 0.1111 | 0.2000 |
| E1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| E2 | 10 | 0.5000 | 0.8000 | 0.6154 |

Errores por identificador ciego: F002, F006, F009, F012, F015, F016, F017, F024, F026, F031, F040.

## Similitud, independencia y alcance

Se verificaron los SHA-256 de las 40 candidatas y las 117 fotografías de entrenamiento. No hay duplicados exactos entre candidatas ni coincidencias de bytes con el piloto. El análisis perceptual previo tampoco detectó duplicados de píxeles y mantiene una relación pendiente: **F014 / TQ_001517** frente a `pilot117_00f307fc985211e52db4`, distancia perceptual mínima 8/63 con transformaciones D4. La igualdad o desigualdad de hashes no prueba identidad física.

La sensibilidad descriptiva, excluyendo F014 por ese indicio previo, deja tomate en n=19, accuracy **0,4211** y F1 macro **0,2051**; matriz `[[0,1,7],[0,0,1],[0,2,8]]`. F014 es un acierto E0 en la evaluación principal. No se seleccionó el mejor resultado ni se ajustó el modelo. Mango permanece igual. Esta exclusión tampoco acredita independencia.

El número de frutas físicamente distintas y sesiones sigue desconocido: hay cero acreditaciones documentales, lo que no significa cero frutas reales. Las candidatas no se utilizaron en el entrenamiento del piloto según el inventario de hashes; algunas pueden pertenecer al desarrollo exploratorio anterior y no constituyen un conjunto nuevo independiente de todo el sistema. **Kent no está acreditado**: el resultado corresponde a mango genérico.

Las clases están desequilibradas: mango E2 y tomate E1 tienen solo una fotografía humana cada una. No hay aprobación de tamaño muestral, medición de acuerdo entre revisores ni soporte para inferir rendimiento general o de producción. No existen mediciones reales emparejadas de tiempos/correcciones manuales frente al flujo asistido; no se afirma reducción de trabajo manual.

## Verificación y preservación

Las 40 predicciones y sus puntuaciones coinciden con el diagnóstico congelado anterior (tolerancia 1e-12). Las matrices y F1 macro se recalcularon mediante conteos separados sin NumPy. Pasaron **32/32 pruebas de visión AG-055**, incluidas seis nuevas de correspondencia de IDs, integridad de columnas, etiquetas y métricas. `vision_tests.log`, `tests_result.json` y `verification.json` conservan evidencia. No se modificaron backend ni frontend; no se repitieron sus suites ni el navegador para esta ejecución fuera de línea.

`integrity.json` coteja antes/después: CSV, mapa, protocolo, auditoría, inventario, 157 fotografías, modelos del piloto, modelos anteriores, ZIP fuente y SQLite original. Todos permanecieron iguales. La base original conserva SHA-256 `c4cac0813ea14e2586e8c49e63e8b32fbbf47929f1f932d8dcaf895521af73e5`. Los resultados individuales, datos y modelos se mantienen fuera de Git. El flujo estricto de evaluación independiente permanece sin cambios.

## Matriz de aceptación para Jira

| Criterio | Estado | Evidencia / restricción |
|---|---|---|
| Comparación de 40 etiquetas humanas con modelos congelados | Cumplido, exploratorio | 40 inferencias y comparación individual |
| Matrices y métricas por producto/clase | Cumplido, exploratorio | n=20 por producto; F1 macro 0,1944 / 0,2718 |
| Preservación de modelos, umbrales, datos y SQLite | Cumplido | SHA-256 antes/después; sin reentrenamiento |
| Identidad y fecha humana | Declaradas | Junior Pérez, 13/11/2026, según usuario; CSV sin esos campos |
| Independencia física y resolución de similitudes | Pendiente | Frutas/sesiones sin acreditar; F014 sin resolver |
| Validación independiente acreditada y rendimiento suficiente | No cumplido | Estudio exploratorio pequeño y desequilibrado; sin criterio cuantitativo aprobado |
| Variedad Kent | Pendiente | Sin evidencia de variedad |
| Rúbrica, soportes y cegamiento efectivo | No acreditado | Campos vacíos en las 40 filas |
| Reducción de revisión manual | No evaluado | Sin tiempos ni correcciones emparejados |

**Estado recomendado para AGROP-67: mantener abierto, con evaluación exploratoria ejecutada y aceptación experimental pendiente.** Este informe no cambia el estado de Jira. No se requieren nuevos formularios para completar esta comparación exploratoria.

## Artefactos privados

Carpeta: `C:\Users\Luigi\Documents\AgroScan_AG055_Evaluacion_Exploratoria_40_20261113_01`.

`report.json`: resultados y atribución; `predictions.json`: etiquetas originales, predicciones y scores sin calibrar; `comparacion.csv`: comparación por imagen; `formulario_completado_original.csv`: copia exacta; `integrity.json`: preservación; logs y `SHA256SUMS.json`: verificaciones.

## Comando mínimo Windows

Desde la raíz del repositorio, usar una carpeta de salida nueva (no sobrescribe evidencias):

```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend;$PWD\backend\.venv\Lib\site-packages"
$env:PYTHONUTF8 = "1"
py -3.13 -m vision.ag055.exploratory40 `
  --package-root "$env:USERPROFILE\Documents\AgroScan_AG055_Revision_Ciega_40_02" `
  --pilot-run "$env:USERPROFILE\Documents\AgroScan_AG055_E0E1E2_117_01" `
  --reviews "$env:USERPROFILE\Downloads\formulario_completado.csv" `
  --reviewer "Junior Pérez" --review-date 2026-11-13 `
  --output "$env:USERPROFILE\Documents\AgroScan_AG055_Evaluacion_Exploratoria_40_20261113_02"
py -3.13 -m unittest discover -s vision/tests -p "test_ag055_*.py" -v
```
