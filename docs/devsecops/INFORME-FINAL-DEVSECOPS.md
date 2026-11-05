# AgroScan — Informe técnico final de auditoría DevSecOps (Incremento 05)

**Fecha del corte:** 4 de noviembre de 2026 (hora de Lima; ejecuciones de GitHub registradas en UTC del 5 de noviembre).
**Repositorio:** `cris0203nh/iot-fruit-classification`.
**Rama evaluada:** `security/devsecops-hardening`. **`main` no se ha fusionado ni modificado mediante estos incrementos.**
**Commit del estado posterior al Incremento 04:** `7b8e2ebb8c567e4e1a715115584afcba5cf3f103`.
**Estado del Incremento 05:** evidencia y ajuste de CI preparados; falta ejecutar y comprobar ambos workflows después de aplicar este parche.

## 1. Objetivo, límites y metodología

Objetivo: integrar la seguridad a la integración continua (SAST, SCA, búsqueda de secretos, QA y DAST), remediar hallazgos verificables y comparar automáticamente el mismo proyecto antes/después, sin llevar modificaciones directamente a `main`.

**Fuentes primarias.** Archivos JSON *normalizados* que generaron Bandit, npm audit, pip-audit, Gitleaks y ZAP, preservados en `docs/devsecops/evidencias/` y verificados con SHA-256 mediante `scripts/devsecops/verificar_evidencias.py`. El manifiesto incluye IDs de ejecución y referencias del commit. La evidencia histórica se conserva porque los artefactos CI originales tienen retención de 14 días. Los reportes crudos no se guardan: podrían contener datos sensibles. El hash verifica integridad respecto del manifiesto local, **no** constituye una firma externa de una autoridad independiente.

**Criterio de conteo.** Los números representan registros emitidos por herramientas, no vulnerabilidades únicas, confirmación de explotación ni CVE distintos. En ZAP se diferencia entre reglas y ocurrencias. Los resultados son válidos **para esos commits, configuraciones, lockfiles y modos de escaneo**, no para cualquier despliegue posterior.

## 2. Comparativa de escáneres de código, dependencias y secretos

| Fuente | Línea base `ce9a16d` | Tras Incremento 02 `2a59115` | Tras Incremento 04 `7b8e2eb` |
|---|---:|---:|---:|
| Bandit: alertas bajas | 2 | 2 | 2 |
| npm audit: paquetes alertados | 11 | 0 | 0 |
| pip-audit backend: registros | 1 | 0 | 0 |
| pip-audit puente serial | 0 | 0 | 0 |
| Gitleaks: coincidencias históricas | 3 | 3 | 3 |
| Gitleaks: secretos introducidos | 0 | 0 | 0 |
| **Total de registros** | **17** | **5** | **5** |

**Reducción de registros:** 12 de 17 (**70,6 %**). La totalidad de los **12 avisos de dependencias inicialmente detectados** deja de aparecer en los reportes SCA del commit evaluado. En el frontend, la corrección de `minimatch` exige un override de versión mayor: aunque lint, pruebas y build pasan en CI, se debe vigilar su compatibilidad cuando se actualicen ESLint o TypeScript ESLint.

**Interpretación del remanente:** Bandit conserva `B105` (literal OAuth2 `bearer`) y `B311` (PRNG determinista empleado para particionar el dataset); son avisos bajos con justificación contextual, no una validación de seguridad de toda la funcionalidad. Gitleaks conserva tres coincidencias **históricas de contraseñas de prueba**, sin valores de secretos nuevos en los reportes. No se eliminó ni reescribió el historial. Debe confirmarse que ninguna credencial histórica se haya reutilizado en un servicio real.

## 3. Comparativa DAST — instancia aislada

| Regla ZAP | Escaneo Incremento 03 (`2954fe0`) | Escaneo Incremento 04 (`7b8e2eb`) | Estado |
|---|---:|---:|---|
| `10021` (LOW): `X-Content-Type-Options` ausente | 2 ocurrencias | 0 | Desapareció |
| `90004` (LOW): aislamiento entre orígenes | 2 | 0 | Desapareció |
| `10049` (INFO): cacheabilidad | 5 | 5 | Informativa |
| `10111` (INFO): solicitud de autenticación | 2 | 2 | Informativa |
| `100000` (INFO): códigos de error HTTP | 22 | 22 | Informativa |
| **Reglas distintas** | **5** | **3** | **-2** |
| **Ocurrencias** | **33** | **29** | **-4** |

En el último artefacto, **0 alertas LOW/MEDIUM/HIGH/CRITICAL**; permanecen tres reglas de severidad informativa. La mejora se consiguió incorporando cabeceras `X-Content-Type-Options: nosniff`, CORP y políticas de caché para las rutas API, con pruebas negativas y CORS. No se configuró COEP global, para no afectar a documentación y recursos externos. La regla `10049` informativa no justifica quitar `Cache-Control: no-store`.

**Límites del DAST:** ZAP se ejecutó con `-S` (sin escaneo activo) sobre OpenAPI y una API temporal sin credenciales de usuarios reales; no se probaron todas las combinaciones autenticadas de roles, IDOR/BOLA, ataques de negocio, entorno productivo, proxy inverso, TLS ni controles del navegador completo. Un gate verde indica que no se alcanzó el umbral de bloqueo, no ausencia absoluta de vulnerabilidades.

## 4. Seguridad funcional implementada

- **Identidad IoT:** el POST de mediciones rechaza claves ausentes/erróneas y valida credenciales por dispositivo (`X-Device-Key`); los tests comprueban que un rechazo no persista datos. Envíos a destinos remotos exigen HTTPS en el puente de prueba.
- **Consulta de estado:** requiere JWT y rechaza tokens inactivos; los permisos de evaluación, gestión de usuarios y evidencias conservan pruebas de autorización.
- **Login:** límite de intentos con HTTP 429 y relleno de verificación de contraseñas para usuarios inexistentes. El contador es **en memoria por proceso**; para despliegue multinodo se necesitará Redis o protección en gateway.
- **HTTP:** respuestas API con `no-store`, `nosniff`, CORP y `Referrer-Policy`, con pruebas de CORS, denegaciones 401/403 y preflight. Los errores originados fuera de la aplicación (proxy o gateway) necesitan configuración adicional.
- **Suministro de dependencias:** acciones de CI principales fijadas por SHA; `npm audit` y `pip-audit` bloquean hallazgos, Bandit bloquea HIGH/CRITICAL y Gitleaks bloquea secretos nuevos. `pip-audit --no-deps` no garantiza auditoría completa de dependencias transitivas no fijadas.

## 5. Estado de integración continua y regresión encontrada

Ejecución posterior al Incremento 04:

- **AgroScan DevSecOps - baseline y controles:** [run 41967242501](https://github.com/cris0203nh/iot-fruit-classification/actions/runs/41967242501), commit `7b8e2eb`, **7/7 jobs correctos**; cinco artefactos generados.
- **Pesaje ESP32 y pruebas de software (workflow heredado):** [run 41967242502](https://github.com/cris0203nh/iot-fruit-classification/actions/runs/41967242502), mismo commit, **falló el job `software`**, aunque `compile-esp32` aprobó. El traceback confirma `RuntimeError: La clave JWT no está configurada correctamente` al importar `app.security` desde `tests/test_iot_firmware_integration.py`.

El Incremento 05 corrige `.github/workflows/pesaje.yml` generando `AGROSCAN_JWT_SECRET` **efímero** en el runner antes de ejecutar las pruebas IoT y definiendo `PYTHONPATH=backend`; no relaja la comprobación JWT de producción. También migra `checkout` y `setup-python` a acciones Node.js 24 fijadas por SHA, fija la acción Arduino v2 por SHA y ejecuta el workflow en `ubuntu-24.04`. La acción Arduino v2 aún declara Node.js 20; **puede seguir mostrando un aviso de obsolescencia** hasta que el proyecto externo disponga de una variante compatible con Node.js 24. No se debe interpretar ese aviso como un fallo de las pruebas de AgroScan.

En la copia aislada, con JWT temporal, **25/25 pruebas de IoT pasaron**. Debe verificarse el resultado definitivo **en GitHub** tras subir este incremento: son dos workflows independientes, por lo que no basta con que el pipeline DevSecOps marque verde.

## 6. Riesgos residuales y decisiones

| ID | Riesgo / limitación | Tratamiento | Condición de cierre |
|---|---|---|---|
| R-01 | Login limitado en memoria por proceso | Aceptable en laboratorio; gateway/Redis para múltiples workers | Antes de exponer servicio multiinstancia |
| R-02 | Cobertura DAST pasiva, esencialmente sin autenticación | Ampliar pruebas autenticadas por rol e IDOR | Antes de clasificar la API como endurecida para producción |
| R-03 | Claves IoT suministradas por entorno, sin gestión centralizada/rotación automatizada | Secret manager, TLS, rotación e inventario | Antes de hardware real distribuido |
| R-04 | `pip-audit --no-deps` y errores de toolchain fuera de alcance | Revisar árbol transitivo y SBOM | Para auditoría de suministro integral |
| R-05 | Bandit B105/B311 y tres coincidencias históricas Gitleaks | Triage contextual sin silenciar globalmente; confirmar que no hay credenciales reales reutilizadas | Revisión manual documentada |
| R-06 | Cabeceras de gateway/HTTPS, CORS y política COEP en producción no validadas | Probar en staging con navegador y proxy real | Antes del despliegue |
| R-07 | Workflow heredado falla en la ejecución anterior | Corregido en parche; nuevo run pendiente | Ambos workflows en verde en la misma revisión |
| R-08 | Acción Arduino v2 usa runtime Node 20 | SHA fijado; seguir release upstream | Migrar cuando exista alternativa compatible |
| R-09 | Esquema de evidencias y datos de pruebas vs producción | No publicar bases SQLite ni `.env`, revisar privacidad/retención | Antes de publicar cualquier artefacto externo |

## 7. Criterios de cierre y decisión

- [x] Ramas y worktree independientes; no se efectuó merge en `main`.
- [x] SAST, SCA, Gitleaks, QA y DAST integrados y evaluados en el pipeline de seguridad.
- [x] Comparativa de reportes antes/después reproducible y hashes verificados.
- [x] Reducción de SCA de 12 a 0 registros y remediación de las dos reglas LOW del DAST verificadas.
- [x] Reportes normalizados históricos guardados sin cuerpos de peticiones ni secretos.
- [ ] **Pendiente tras aplicar este incremento:** nueva ejecución aprobada del workflow `Pesaje ESP32 y pruebas de software`.
- [ ] **Pendiente tras aplicar este incremento:** nueva ejecución aprobada de `AgroScan DevSecOps` incluyendo el verificador de evidencias.
- [ ] Revisión humana y aceptación de riesgos residuales antes de cualquier Pull Request o merge.

**Dictamen:** el **alcance académico de integración y comparativa DevSecOps está sustancialmente desarrollado y respaldado por evidencia**; el cierre técnico de CI queda condicionado a que ambos workflows aprueben con el parche del Incremento 05. **No equivale a certificación, pentest completo ni autorización de despliegue productivo.**

## 8. Reproducción y trazabilidad

Desde el worktree `iot-fruit-classification-devsecops`:

```powershell
& .\backend\.venv\Scripts\python.exe scripts/devsecops/verificar_evidencias.py
& .\backend\.venv\Scripts\python.exe -m unittest discover -s scripts/devsecops -p "test_*.py" -v
$env:AGROSCAN_JWT_SECRET = & .\backend\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
$env:PYTHONPATH = "backend"
& .\backend\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

La versión estructurada se encuentra en `docs/devsecops/RESULTADOS-FINALES.json`. Los reportes históricos originales se vinculan por run ID en `docs/devsecops/evidencias/manifest.json`; el script de verificación falla si falta un reporte, su contenido no coincide con su SHA o sus conteos son inconsistentes.
