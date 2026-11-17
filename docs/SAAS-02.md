# SaaS-02 — SQLite para multiempresa

SQLite permanece como motor principal. Sin organizaciones, membresías, roles nuevos ni migraciones en este incremento. No se activó WAL en la base original.

## Correcciones reproducidas

- Restauración con WAL residual tras cierre abrupto reaplicaba datos posteriores al respaldo y fallaba la correspondencia con fotografías. Ahora se hace checkpoint y cierre de WAL mediante SQLite antes de sustituir archivos; si está ocupado se rechaza sin sustituirlos. Se conserva el modo WAL tras restauración o rollback. Formato ZIP y endpoints conservados.
- Dos reenvíos IoT simultáneos de una secuencia provocaban `IntegrityError`. Ahora se recupera la lectura confirmada y se devuelve el contrato existente de duplicado, sin cambiar fecha ni crear otra fila. Reproducido y corregido en DELETE y WAL.

## Verificación en copia aislada

- Copia consistente desde fuente SQLite `mode=ro`; operaciones de escritura, WAL, respaldo y restauración solo en temporales. **18 tablas, 35 índices, integridad OK y cero violaciones FK**; sin cruces lote/pieza ni evaluación/imagen de decisiones en los datos comprobados. Sin colisiones de códigos de lote al comparar en minúsculas.
- Comparación Alembic/modelos: dos diferencias de representación equivalentes (índice único frente a restricción de idempotencia de imágenes; nombre del índice de evaluación en decisiones). No requieren alterar datos ni esquema.
- 11 FK hijas sin índice cuyo prefijo cubra la relación: `evaluations.weight_{pre,post}_measurement_id`, `user_roles.role_id`, `review_decision_evidence.image_id`, `vision_prechecks.{evaluation_id,registered_lot_id}`, `ag054_planar_calibrations.{operator_id,geometry_id}`, `ag054_board_calibrations.{operator_id,geometry_id}`, `ag054_dimensional_comparisons.operator_id`. No implican pérdida de integridad; evaluar índices junto al esquema de organizaciones, sin duplicar los existentes.
- Copia real puesta en WAL: respaldo/restauración de **35 imágenes vinculadas y 86 archivos**, SQL completo y SHA-256 de fotos idénticos; WAL conservado.
- **72 pruebas OK**, reutilizando respaldo/API/integración, integridad y bloqueo AG-046, autorregistro AG-053, decisiones y estado IoT. Ampliaciones: conexiones FK realmente independientes, concurrencia DELETE/WAL, snapshot lector, rollback y escritor ocupado, WAL residual, fallo de instalación con WAL y rechazo de lector WAL activo. Detector simulado como en las pruebas existentes. `git diff --check` OK; build/lint frontend no aplican.

## Límites y criterios para SaaS-03

- SQLite permite un escritor a la vez. WAL mantiene lectores concurrentes y snapshots estables, no escritores paralelos. La espera actual de conexión es 5 s; transacciones largas pueden agotarla. Mantener transacciones cortas y reintentos idempotentes; no añadir reintentos ciegos. WAL probado, habilitación operativa pendiente de mantenimiento autorizado.
- Respaldos siguen siendo globales. El bloqueo de aplicación sigue limitado a un proceso y no cubre lecturas; la comprobación de WAL no es un bloqueo distribuido. Restaurar en mantenimiento, sin otros workers, lectores ni escritores externos. Sin garantía frente a caídas entre sustituciones físicas de BD/fotos.
- Antes de agregar organizaciones: definir organización inicial de datos existentes, membresías y alcance de administración. Diseñar claves únicas e índices por organización según consultas; FK compuestas que impidan cruces organización/lote/pieza/evaluación/imagen/dispositivo. `CHECK` para invariantes de la misma fila; no usarlo para pertenencia entre tablas.
- Definir normalización/unicidad de usuarios y códigos: búsquedas actuales por `lower(code)` no equivalen a una unicidad normalizada en BD. Identidad y roles siguen globales; no exponer instancia compartida hasta resolver también autenticación IoT y selección de lecturas señaladas en SaaS-01.
- Criterio de aceptación de SaaS-03: migración SQLite reversible ensayada sobre copia, conteos/relaciones/fotos conservados y `foreign_key_check` limpio; membresías y accesos cruzados probados con dos organizaciones, sin filtrar únicamente en frontend. PostgreSQL fuera del alcance actual.

SaaS-03 no implementado. Sin cambios en datos originales, frontend, IA, firmware ni dependencias; sin commit/push.
