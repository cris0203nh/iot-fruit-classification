# AgroScan — Ajuste de cierre del Incremento 02 (CI)

**Ámbito:** `security/devsecops-hardening`; sin cambios funcionales en frontend, backend ni firmware.
**Referencia:** pipeline aprobado en `2a59115`, sobre el cual se aplica este parche.

## Motivo

La segunda ejecución de GitHub Actions aprobó los seis jobs, pero mostró seis advertencias de deprecación de Node.js 20 en las GitHub Actions reutilizadas. Los cuatro artefactos de seguridad registraron `npm audit: 0` y `pip-audit: 0` alertas; se habilita un gate de npm para impedir reintroducciones en futuras ejecuciones.

## Acciones actualizadas y verificadas

| Acción | Ref anterior | Nueva versión fijada por SHA | Runtime verificado |
|---|---|---|---|
| `actions/checkout` | v4.2.2 | v5.0.1 — `93cb6efe18208431cddfb8368fd83d5badbf9bfd` | `node24` |
| `actions/setup-python` | v5.6.0 | v6.0.0 — `e797f83bcb11b83ae66e0230d6156d7c80228e7c` | `node24` |
| `actions/setup-node` | v4.4.0 | v5.0.0 — `a0853c24544627f65ddf259abe73b1d18a591444` | `node24` |
| `actions/upload-artifact` | v4.6.2 | v6.0.0 — `b7c566a772e6b6bfb58ed0dc250532a479d7789f` | `node24` |

Cada SHA fue contrastado con su ref etiquetada y su `action.yml` en el repositorio oficial de GitHub. Se mantiene el Node.js 22 del proyecto frontend: el Node.js 24 es únicamente el **runtime interno de las acciones**.

## Nuevo gate de npm

- El job `Dependencias frontend (gate)` conserva `npm audit --prefix frontend --json --audit-level=low`.
- El normalizador ahora se invoca con `--fail-findings`: **cualquier vulnerabilidad reportada** bloquea el job, incluso de severidad baja.
- Un JSON malformado, una falla operativa o un `exit code` inesperado también bloquea el job.
- El reporte `reports/npm.json` conserva el conteo sanitizado para evidencia; se borra `reports/npm-raw.json` antes de subir artefactos.
- No se cambia `package.json` ni `package-lock.json`. Si una nueva advisory aparece en el futuro, la ejecución puede fallar de forma esperada: se debe corregir la dependencia o documentar el análisis y ajustar la política de forma explícita, nunca omitir los escaneos.

## Validación local y remota

Desde la raíz del worktree DevSecOps (PowerShell):

```powershell
python -m unittest discover -s scripts/devsecops -p 'test_*.py' -v
git diff --check
git diff -- .github/workflows/devsecops.yml scripts/devsecops/normalize_scan.py scripts/devsecops/test_normalize_scan.py
```

Tras registrar y publicar únicamente la rama `security/devsecops-hardening`, comprobar en **Actions > AgroScan DevSecOps - baseline y controles**:

1. Los seis jobs deben aprobarse.
2. El job `Dependencias frontend (gate)` debe terminar en verde; su artefacto `npm.json` debe mostrar `finding_count = 0`.
3. El apartado `Annotations` no debería repetir las seis advertencias de Node.js 20 para este workflow.
4. Los cuatro artefactos deben estar disponibles; en caso de error, analizar logs del job sin publicar raw secrets.

**Importante:** GitHub Actions todavía debe ejecutar el workflow nuevo. La validación local no garantiza por sí sola la ausencia de advertencias en los runners remotos.
