# Etapa 06 — Reportes CI y controles de integración

Base: `main` después del PR #88 (`f847871f41c5b7cc97f5b651a5d098d720e11d6a`).

## Cambios implementados

1. **Informe global estable** en `CI - validación global`, generado por `scripts/ci/check_gate.py`.
   En `GITHUB_STEP_SUMMARY` aparecen: selección, resultado esperado, resultado observado,
   cumplimiento, omisiones justificadas y condiciones incumplidas.
2. **Artefacto JSON sanitizado** `agroscan-ci-global` (`reports/ci-global.json`), retención de 14 días.
   Contrato `schema_version=1`, `decision=approved|rejected`, estados solo de una lista permitida,
   contexto de ejecución validado y violaciones sin datos privados.
3. **Fail-closed**: si falla un job requerido, existe una omisión inesperada, se altera una
   variable de selección o no puede generarse el artefacto, `CI - validación global` falla.
4. Plantilla de Pull Request con objetivo, pruebas y riesgo residual. La plantilla es orientativa,
   **no es un control de obligatoriedad** de la descripción.
5. Los artefactos sanitizados SAST/SCA/Gitleaks/ZAP introducidos en Etapa 04 permanecen disponibles;
   no se capturan ni publican logs/archivos sin filtrar.

## Ejecución y trazabilidad

GitHub → PR → Checks → `AgroScan CI - pipeline segmentado` → `CI - validación global`:
- Consultar **Summary** (tabla de módulos, selected/skipped y estados).
- En **Artifacts**, descargar `agroscan-ci-global` y, para seguridad, los reportes normalizados.
- Para pruebas de cada módulo, abrir su job y revisar los logs (el JSON global no incluye
  métricas de cobertura ni cuenta automáticamente test-cases individuales).

**No confundir** `success` de un módulo con un test físico validado: ESP32/cámara/báscula
físicos y la precisión E0/E1/E2 necesitan evidencia experimental independiente.

## Activación de verificaciones obligatorias en GitHub (paso administrativo)

> La conexión de GitHub utilizada para preparar esta etapa no dispone de acceso
> a protección tradicional de ramas. Al consultar las rulesets públicas no apareció ninguna.
> Por tanto, **la protección de `main` NO está configurada por este parche**.

Un administrador del repositorio deberá completar en GitHub:

1. **Settings → Rules → Rulesets → New branch ruleset** (o Branches → protección de rama,
   según permisos/interfaz). Configurar destino `main` y enforcement `Active`.
2. Activar **Require a pull request before merging**.
3. Activar **Require status checks to pass before merging** y seleccionar el check exacto
   `CI - validación global` de una ejecución reciente de GitHub Actions.
   Puede aparecer sin prefijo de workflow; elegir el check real en la lista, nunca inventarlo.
4. Preferir checks estrictos (rama actualizada con `main`), bloquear force-push y valorar una revisión
   aprobatoria independiente según la capacidad real del equipo.
5. Guardar. Verificarlo con un PR de prueba en el que el check final falle deliberadamente;
   **el botón Merge debe permanecer bloqueado**. Retirar la prueba fallida sin fusionarla.
6. No marcar como obligatorio un job que pueda aparecer `skipped` por la selección de Etapa 05:
   se exige el **gate final estable**, que valida todas las dependencias.

Si se habilita *merge queue*, será necesario agregar `merge_group` al workflow antes de exigir la cola.

## Validación requerida para el PR de esta etapa

- Ejecutar `python -m unittest discover -s scripts/ci -p 'test_*.py' -v`.
- Comprobar sintaxis de YAML/Actions y `git diff --check`.
- Un cambio `.github/workflows/ci.yml` debe activar ejecución completa.
- Comprobar en GitHub Actions `agroscan-ci-global` con `decision=approved` cuando estén todos verdes.
- Probar con fallo simulado local que el informe indique `rejected` y el ejecutable devuelva código 1.
- **No fusionar el PR** si falla una validación obligatoria o no se publica el artefacto.

## Límites y seguridad

- El informe global incluye solamente estados enumerados y metadatos de GitHub validados;
  no replica hallazgos crudos, URLs sensibles, cabeceras HTTP ni secretos.
- Se mantiene la excepción temporal de `picomatch` vigente hasta **2026-12-01 00:00 UTC**.
  El éxito del check SCA debe leerse con ese riesgo residual. La excepción caduca por código.
- No se altera lógica de FastAPI/React/visión/IoT, bases SQLite, firmware ni seguridad SaaS.
- La configuración de protección GitHub es manual y debe comprobarse por separado.
