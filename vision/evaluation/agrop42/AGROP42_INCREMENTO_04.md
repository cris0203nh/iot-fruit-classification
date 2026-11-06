# AgroScan — AGROP-42 · Incremento 04

## Objetivo y alcance

Consolidar las **19 preanotaciones descriptivas** aceptadas el 05/11/2026 y preparar un experimento reproducible **sin atribuir resultados inexistentes**. No se cambian la API, el frontend ni el importador AGROP-42 01A, y no se realizan publicaciones remotas.

## Entregables

- `AGROP42_revisiones_texto_aprobado_v2.csv`: conserva el esquema de 39 columnas, los 19 identificadores, los SHA-256, procedencia y licencia del inventario; `revisada` solo indica revisión textual del encuadre y **no** certifica clases E0/E1/E2.
- `auditar_revisiones.py`: control adicional de integridad, grupos y etiquetas. No reemplaza `auditoria.json` ni el validador previo.
- `AGROP42_comparacion_condicionada.ipynb`: cuaderno para diseño y, solo cuando existan datos suficientes, comparación entre referencia estadística y un clasificador de atributos. Los atributos **deben tener validación de máscara y trazabilidad**.
- `vision/tests/test_agrop42_consolidacion.py`: pruebas unitarias del bloqueo y antileakage.

## Criterio por registro

| Registros | Estado de la descripción | Fundamento | Clase E0/E1/E2 |
|---|---|---|---|
| REG-00001, 00003, 00004 | `no_evaluable` | Varios frutos o falta de detalle para evaluar individualmente | Sin asignar |
| REG-00005–00008 | `no_evaluable` | Múltiples tomates sin identificación de cada pieza | Sin asignar |
| REG-00002, 00009–00019 | `revisada` | Hay detalles observables en la vista descrita; no se confirma la inspección completa | Sin asignar |

**Importante:** los 12 estados `revisada` no constituyen verificación por operador de fotografías, procedencia de lote, cobertura, variedad real ni sesión. El acuerdo del solicitante se limita a la redacción. `revisor_id`, `revisado_en`, `calidad_confirmada`, `cobertura_confirmada`, etiquetas, lote, pieza y sesión permanecen **vacíos**.

## Puerta de experimentación

Se exige por producto (mango y tomate):

1. **≥3 grupos realmente independientes**, uniendo muestras que compartan pieza **o** sesión, para reducir fuga entre particiones.
2. **≥2 clases E0/E1/E2** trazables mediante revisión registrada (revisor, fecha, rúbrica, justificación, evidencia de pieza/sesión, calidad y cobertura confirmadas).
3. Sin SHA-256 duplicados, registros repetidos o rutas inseguras.

El umbral es una condición **mínima**, no un tamaño muestral suficiente para declarar desempeño. El cuaderno exige además descriptores de máscaras confirmadas y particiones con al menos dos clases en entrenamiento y prueba.

Con el inventario actual: **4 fotos de mango, 15 de tomate; 0 etiquetas E0/E1/E2 admisibles; 0 grupos acreditados en cada fruta**. Ambos productos quedan bloqueados; por tanto **no hay precisión, F1 ni comparativa de algoritmos ejecutada**.

## Ejecución PowerShell desde raíz del repositorio

```powershell
.\backend\.venv\Scripts\python.exe -m unittest vision.tests.test_agrop42_consolidacion -v
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar_revisiones `
  --csv vision/evaluation/agrop42/AGROP42_revisiones_texto_aprobado_v2.csv `
  --output vision/experiments/AGROP42/AGROP42_incremento04_auditoria.json
```

Abrir el cuaderno `vision/evaluation/agrop42/AGROP42_comparacion_condicionada.ipynb` en un entorno Jupyter **solo** para inspeccionar las condiciones; la evaluación se omite mientras permanezca el bloqueo. Para volver a revisar el conjunto, conservar originales y crear una nueva versión de CSV, registrando verdaderas evidencias humanas antes de modificar campos de etiqueta/trazabilidad.

## Dependencias pendientes

- Registrar muestras físicas individuales (o fuente con mapa inequívoco de piezas), sesiones, vistas, captura y autorización de uso.
- Completar material evaluable de mango (11 fotos aún faltantes respecto a la meta documental de 15, pero 15 fotos no garantizan independencia).
- Revisión por operador de calidad/cobertura y etiqueta E0/E1/E2, con criterio y justificación; no deducir enfermedad ni estado interno a partir de RGB.
- Máscaras validadas y descriptores numéricos trazables para poder evaluar dos enfoques sin mezcla de grupos.
