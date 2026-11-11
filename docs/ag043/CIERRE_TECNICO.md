# AG-043 / AGROP-51 — Cierre técnico del software con limitaciones

**Proyecto:** AgroScan — iot-fruit-classification  
**Fecha de corte:** 11/11/2026  
**Alcance de cierre:** desarrollo de software, integración y pruebas automatizadas con entradas controladas.  
**Estado:** implementación automatizada completada; validación física y comprobación visual en navegador pendientes.

## Funcionalidad integrada

- Flujo de adquisición de mango y tomate con vinculación entre lote, pieza y evaluación.
- Registro de pesos anterior y posterior y obligación de dos fotografías de la misma evaluación antes de confirmar.
- Validaciones negativas, comprobación de identidad, trazabilidad y reporte por lote.
- Conciliación UX/UI y presentación por roles: operador, revisor y administrador.
- Ajustes de navegación, accesibilidad e indicadores de hardware no verificado.

## Evidencia disponible

Se conserva en `docs/ag043/validacion_20261111_175355/` la ejecución automatizada del 11/11/2026:

| Control | Resultado registrado |
| --- | --- |
| Pruebas E2E HTTP AGROP-51, mango y tomate | 3/3 aprobadas |
| Regresiones de adquisición AGROP-45 | 8/8 aprobadas |
| Pruebas frontend, antes del último ajuste de roles | 85/85 aprobadas |
| Compilación TypeScript + Vite | Aprobada |
| `git diff --check` | Aprobado |

**Nota:** después de la generación de este reporte se aplicaron ajustes adicionales de roles. Debe conservarse un registro de la nueva ejecución de `npm test` y `npm run build` antes de fusionar el PR; no se atribuye a este informe una ejecución que no contiene.

## Límites y pendientes

1. Las pruebas E2E utilizan FastAPI real y SQLite temporal, con lecturas e imágenes controladas. No constituyen validación física de balanza ESP32 o cámara RGB.
2. La navegación funcional en un navegador conectado a FastAPI no queda acreditada por las pruebas unitarias ni por la compilación.
3. La prueba de auditoría AG-038 presentó anteriormente un bloqueo de permisos de directorios temporales, ajeno a esta suite de validación; no se declara superado.
4. No se declara desempeño operativo de hardware ni precisión física del detector a partir de simulaciones.

## Criterio de cierre

Se propone cerrar **el alcance de software y pruebas automatizadas de AG-043** y mantener las comprobaciones de navegador, hardware y AG-038 como pendientes expresamente identificados. Si los criterios de aceptación de AGROP-51 exigen validación física, esa actividad no debe marcarse como `Done` hasta ajustar formalmente el alcance o aportar las evidencias requeridas.

## Trazabilidad de integración

- Rama propuesta: `feature/AG043-cierre-software`.
- Integrar mediante pull request dirigido a `main`.
- Adjuntar o enlazar el reporte de validación y registrar en el PR los resultados reales de las pruebas posteriores a los ajustes de roles.
- No incluir archivos de datos operativos, secretos, entornos virtuales ni trabajo independiente de AG-034/AG-036.
