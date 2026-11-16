# AG-046 / AGROP-54 — Incremento 05: plan de cierre documentado

**Corte de diseño:** 2026-11-16. **Evidencia previa:** resultados comunicados por el ejecutor local del responsable, aún por conciliar directamente con sus archivos JSON y logs. No confundir aprobación automatizada con certificación productiva.

## 1. Resultados comunicados

| Fase | Evidencia comunicada | Alcance |
|---|---:|---|
| I01 | 34 controles inventariados y checklist aplicado | Auditoría estática inicial |
| I02 | 87/87 pruebas aprobadas, 16/11/2026 13:23:52 UTC | JWT, roles, decisiones, frontend fuente; SEC-11/12 siguen pendientes |
| I03 | 61/61 pruebas aprobadas, 16/11/2026 14:13:29 UTC | SQLite, fotos, hashes, respaldo y BKP-05 de un proceso |
| I04 | 4/4 controles aprobados, 16/11/2026 14:42:23 UTC | Tres instancias secuenciales Uvicorn sobre sandbox temporal |

Las ejecuciones exactas seleccionadas están declaradas en `backend/audit/ag046_i05_consolidar.py`. El script debe validar sus archivos *locales*, comprobar logs y crear un manifiesto SHA-256. Si faltan fuentes, emitirá `CONSOLIDACION_INCOMPLETA`, no fabricará una aprobación.

**Observación de logs I04 (R1):** el host de auditoría configura Uvicorn
con `log_level='warning'` y `access_log=False`. Una ejecución correcta puede
crear tres archivos `uvicorn_proceso_N.log` de **0 bytes**; no deben presentarse
como evidencia de arranque. El consolidador admite esos archivos vacíos únicamente
si están presentes y el JSON contiene estado aprobado, PID distintos, tres
arranques, dos paradas controladas, una forzada, checkpoints y comparaciones
API/SQLite/SHA-256. La ausencia de un archivo, o una inconsistencia de esos
datos, mantiene el bloqueo. La matriz y el manifiesto marcan los logs vacíos.

## 2. Correcciones y tratamiento de hallazgos

- **H02 / BKP-05, defecto confirmado:** se observó alta de lote mientras estaba activa la suspensión de respaldo. El guard HTTP incorporado se verificó en la batería I03 posterior. Se limita a un proceso FastAPI; no declarar protección entre workers o escritura externa a la API.
- **H04 / BUG-001 / MNT-01:** README desactualizado; este incremento lo corrige, documentando JWT, Alembic, respaldos y limitaciones, y eliminando la instrucción peligrosa de borrar SQLite.
- **H05 / RST:** brecha de evidencia cubierta mediante tres procesos Uvicorn consecutivos, con apagado normal y forzado después de HTTP confirmado; no es prueba sobre despliegue remoto ni corte de energía en transacción.
- **Fallos de pruebas, no de producción:** token Unicode I02, fixtures históricos de revisión, conexiones SQLite temporales Windows, aceptación de sandbox I04 y ruta temporal de apagado. Conservar en historial, no presentarlos como vulnerabilidades productivas.

## 3. Pendientes que NO deben marcarse como aprobados

| Identificador | Estado | Acción exigida |
|---|---|---|
| SEC-11 / H01 | Riesgo abierto | Definir exposición real y autenticación de estación/puente IoT; ensayar la denegación de solicitudes anónimas antes de publicar la API |
| SEC-12 / H03 | Decisión funcional | Confirmar con el equipo la separación de roles de anotación experimental y decisión formal |
| SEC-04 | Validación parcial | Ejecutar interacción en navegador para login, logout, restricción de rutas y persistencia nula del JWT |
| BKP-05 | Verificado en un proceso | Definir número de workers e impedir restauraciones concurrentes entre instancias/procesos externos; examinar consultas GET durante sustitución |
| INT-08 / H06 | Cobertura histórica limitada | Determinar política de hash al capturar nuevas evidencias; no retroacreditar fotos anteriores sin fuente |
| RST / despliegue | Solo sandbox local | Verificar recuperación bajo configuración operativa si el proyecto exige producción |

## 4. Criterio de cierre

**Admisible:** `CIERRE_TECNICO_AUTOMATIZADO_CON_PENDIENTES`, si I02, I03 e I04 se concilian en archivos originales, el README corregido supera la comprobación documental, el inventario I01 tiene 34 controles y el registro de riesgos conserva los pendientes.

**No admisible:** cerrar sin reservas AGROP-54, afirmar seguridad global, hardware verificado, despliegue multiproceso, revalidación de datos operativos o tareas publicadas en GitHub/Jira sin sus evidencias.

## 5. Evidencia para Jira y Git

Ejecutar el consolidador en la raíz del repositorio:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\audit\ag046_i05_consolidar.py
```

Generará **solo** archivos de resumen en `docs/ag046/`:

- `AG046_I05_CIERRE_EVIDENCIADO.md`
- `AG046_I05_MATRIZ_FINAL.csv` (34 controles)
- `AG046_I05_REGISTRO_DEFECTOS.csv`
- `AG046_I05_MANIFIESTO_SHA256.csv` (hash, tamaño y ruta relativa de cada fuente)
- `AG046_I05_TEXTO_JIRA.txt`

Los logs originales permanecen en `docs/ag046/runs/` y **no** se copian ni se adjuntan automáticamente. Revisar posibles datos sensibles antes de compartirlos.

## 6. Publicación selectiva

1. Inspeccionar `git status --short`, `git branch --show-current`, `git diff --cached --name-only` y `git diff -- backend/app/main.py backend/README.md backend/tests/test_agrop47_permissions.py`.
2. **No** usar `git add .`, `git add docs/ag046/` ni `git clean` porque existen archivos ajenos y logs temporales dentro de `docs/ag046/runs/`.
3. Preparar únicamente archivos estáticos del proyecto AG046 y los resúmenes I05 revisados; no añadir `docs/ag046/runs/` sin revisar su contenido.
4. No crear commit si existen archivos ajenos previamente preparados (`git diff --cached --name-only`). Verificar el índice y el cambio de `main.py` antes de publicar.
5. En la rama de demo Vercel, el historial puede contener cambios fuera de AG046. Revisar el diff del futuro PR respecto a su destino antes de fusionar.
6. Adjuntar el resumen y la matriz a Jira y solicitar aceptación de los controles pendientes. El consoli­dador no modifica Jira ni GitHub.
