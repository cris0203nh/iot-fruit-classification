# AgroScan — AGROP-42 · Incremento 05 — Endurecimiento del auditor

## Alcance ejecutado

Se refuerza el **control documental de integridad** de AGROP-42 sobre el Incremento 04, sin realizar entrenamiento ni asignar clases a las fotografías existentes. El cambio no altera los CSV, las imágenes, el backend, las rutas de la API ni el frontend.

- Normaliza la comparación de las huellas SHA-256 para detectar duplicados aunque mezclen mayúsculas y minúsculas.
- Rechaza rutas absolutas o relativas inseguras propias de Windows y POSIX, con independencia del sistema operativo en el que se ejecute la auditoría.
- Bloquea etiquetas E0/E1/E2 en filas con estado `pendiente` o `no_evaluable`.
- Bloquea etiquetas contradictorias acreditables de la **misma pieza en el mismo lote**, incluso si las vistas pertenecen a diferentes sesiones. **No** considera contradictorias dos clases de piezas diferentes capturadas en una misma sesión.
- Detecta filas que contienen más columnas que las declaradas por su encabezado.
- Conserva la interfaz `auditar_csv()` y el CLI, y la distinción entre `apto_para_diseno_experimental` y entrenamiento ejecutado.

## Limitaciones que no resuelve el incremento

La existencia de una cadena con formato SHA-256 no prueba que el archivo digital exista ni que su contenido coincida. Este módulo comprueba **consistencia del inventario**, no lectura forense de los bytes ni autoría de los respaldos. La revisión visual humana, la identidad de cada fruta, la verificación de lotes/sesiones, las licencias, la calidad de captura, las máscaras y las etiquetas siguen siendo requisitos independientes. No modificar los 19 registros para forzar la aprobación del gate.

## Estado de la auditoría recuperada

El Incremento 04 sigue dando **4 fotografías de mango, 15 de tomate, 0 etiquetas elegibles y 0 grupos acreditados**. El estado esperado es `bloqueado_por_datos_insuficientes`. La ausencia de métricas del modelo es correcta.

## Verificación local en Windows

Ejecutar desde la raíz del repositorio:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest vision.tests.test_agrop42_consolidacion vision.tests.test_agrop42_integridad_incremento05 -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar_revisiones `
  --csv vision/evaluation/agrop42/AGROP42_revisiones_texto_aprobado_v2.csv `
  --output vision/experiments/AGROP42/AGROP42_incremento04_auditoria.json

git diff --check
git status --short
```

> Nota Git: `git diff --check` no inspecciona archivos sin seguimiento. Mantener `entrada_fotos/`, bases de datos, credenciales y originales externos fuera de commits hasta revisar permisos, uso permitido y el `.gitignore`. Para revisar archivos nuevos ya añadidos deliberadamente al índice, utilizar `git diff --cached --check`.

## Continuación funcional

El desarrollo siguiente deberá preparar el ingreso auditable de **capturas propias reales y multivista** y su validación por un revisor. Se requiere registrar `pieza_id`, `lote_id`, `sesion_id`, dispositivo, fecha, vistas, resolución/foco, cadena de custodia, autorización, rúbrica y etiqueta con justificación. Sin estas evidencias no procede entrenamiento ni comparación de desempeño.
