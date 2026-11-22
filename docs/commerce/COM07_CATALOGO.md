# COM-07 · Administración del catálogo DEMO

Se amplían `CommercialPlan`, el router y el editor existentes. La identidad es
`code`; cada guardado del editor crea una versión inmutable en borrador. Publicar
requiere confirmación y retira la versión pública anterior. El historial incluye
condiciones, autor, fechas reales disponibles y resumen de cambios. Los límites
siguen siendo informativos. No hay eliminación de planes ni cobros reales.

API compatible:
- `POST /api/platform/commercial/plans`: añade `publish`, `displayOrder`,
  `expectedVersion`, `idempotencyKey`, `changeNote`. El editor envía `publish:false`;
  los clientes c009 conservan su publicación explícita y respuesta originales.
- `PATCH /api/platform/commercial/plans/{id}/status`: publicar/activar/desactivar;
  nunca cancela suscripciones. Impide reactivar versiones publicadas superadas.
- `GET /api/platform/commercial/plans/{id}/versions`: historial privado del propietario.
- `GET /api/commercial/plans`: misma fuente pública, solo versiones activas
  publicadas, ordenadas por posición y código; no expone autor ni notas internas.

`c017catalog` es aditiva tras `a016sessions`: orden, indicador de publicación,
fechas, autor, referencia/hash de creación y nota. No modifica snapshots, IDs,
precios ni fechas contractuales. Las fechas históricas desconocidas quedan nulas.
Los reintentos usan clave/hash y las ediciones comparan la última versión bajo
`BEGIN IMMEDIATE`. Desactivar una versión no invalida su historial.

Prueba contractual automatizada: contratar S/199 mensual → guardar S/249 mensual
con otros beneficios/límites → publicar → solicitud nueva a v2; la suscripción
original completa, incluyendo fechas e identidad, sigue idéntica; una tercera
versión anual también conserva el contrato original. Además se
prueban permisos A/B, concurrencia, rollback y migración/reversión en SQLite temporal.

## Comprobación manual DEV (no ejecutada sobre bases existentes)

1. Detener DEV con Ctrl+C; conservar QA y la base histórica. Hacer respaldo SQLite
   consistente con `Connection.backup` en carpeta privada y verificar
   `integrity_check` y `foreign_key_check` antes de migrar.
2. En una terminal dedicada, desde la raíz, apuntar **solo** a DEV:

```powershell
$py = "$env:USERPROFILE\Documents\AgroScan-Python-Probe\Scripts\python.exe"
$env:AGROSCAN_DATA_DIR = "$env:USERPROFILE\Documents\AgroScan-Dev\data"
$env:AGROSCAN_DATABASE_URL = 'sqlite:///' + ($env:AGROSCAN_DATA_DIR.Replace('\','/') + '/agroscan.db')
Push-Location backend
try { & $py -m alembic upgrade c017catalog; & $py -m alembic current } finally { Pop-Location }
```

3. Arrancar backend con `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
   tools/agroscan_dev.ps1 -Action backend`; en otra terminal `npm --prefix frontend run dev`.
   Los arranques DEV/QA exigen c017 y nunca migran automáticamente. No iniciar QA
   hasta autorizar y preparar por separado su migración.
4. Propietario → Planes y contrataciones DEMO → Catálogo → Nuevo plan/Editar →
   Guardar borrador → Ver versiones → Publicar versión. Comprobar `/planes`, landing
   y `/solicitar?plan=ID`; la selección debe usar el ID de la nueva versión.

Reversión: `alembic downgrade a016sessions` solo sin versiones creadas después de
la migración. Con auditoría nueva, se bloquea para no perder trazabilidad; restaurar
un respaldo consistente requiere decisión explícita. No se migró DEV, QA ni la base histórica.

Limitación de validación del árbol recibido: lint/TypeScript globales señalan
`calculateDimensions` sin uso en `EvaluationEvidenceSnapshot.tsx:126`, ajeno al
catálogo. El navegador real y OAuth/SMTP reales requieren comprobación externa.

Resultados ejecutados: suite backend 557 casos, 554 aprobados y 3 omisiones
preexistentes (fotografías/piloto real y symlinks Windows); 9 pruebas nuevas del
catálogo aprobadas. Frontend 227 aprobadas, sin omisiones. Guardas DEV/QA: 4 y 5
pruebas aisladas aprobadas. ESLint focalizado y empaquetado Vite aprobados;
`npm run lint`, `tsc -b` y `npm run build` globales bloqueados por el error anterior.
Dictamen: catálogo implementado; cierre técnico pendiente del build global y
validación visual en navegador. No se declara COM-07 completamente aprobado.
