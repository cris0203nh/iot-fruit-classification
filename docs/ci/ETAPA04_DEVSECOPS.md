# Etapa 04 — Seguridad DevSecOps integrada al CI segmentado

Base revisada: `main` posterior al PR #86 (`8266529`). **Este cambio no supone que ya se haya validado el nuevo workflow en GitHub**.

## Arquitectura

`Preparación` → en paralelo `Backend`, `Frontend`, `IoT` (2), `Visión`, `Seguridad` (SAST, SCA Python, SCA npm, Gitleaks, pruebas normalizador), `DAST` (ZAP pasivo) → `CI - validación global`.

Los dos nuevos workflows son reutilizables (`workflow_call`), **sin triggers independientes**. No se altera el contrato anterior de los módulos. El agregador rechaza cualquier job requerido con estado distinto de `success`, incluyendo omitidos/cancelados.

## Seguridad y umbrales

| Control | Alcance | Condición de bloqueo |
|---|---|---|
| Bandit | Código Python productivo (`backend/app`, `backend/dataset`, `firmware/tools`, `vision/src`, `vision/ag055`) | Hallazgos HIGH o CRITICAL |
| pip-audit | Requisitos fijados de backend y puente IoT | Cualquier advisory, o error operativo |
| npm audit | Lockfile completo, incluido desarrollo | HIGH o CRITICAL no exceptuado, o error operativo |
| npm audit --omit=dev | Dependencias de producción | Cualquier hallazgo, sin excepciones, o error operativo |
| Gitleaks | Commits introducidos respecto a SHA base PR/push | Cualquier secreto detectado, o error operativo |
| ZAP | OpenAPI de FastAPI local; `-S` **sin escaneo activo** | HIGH o CRITICAL, o error operativo |

El repositorio tenía un DevSecOps anterior en `security/devsecops-hardening`. Se reaprovechan herramientas, el principio de sanitización de resultados y los umbrales; **no** se fusiona esa rama desactualizada ni su código productivo.

Los JSON crudos de escáneres (Gitleaks, ZAP y auditorías) se eliminan. Solo se conservan informes normalizados durante 7 días. Los reportes no incluyen cuerpos HTTP, URL con parámetros, contraseñas ni coincidencias de secretos. Mantenerlos en la revisión de acceso restringido del repositorio.

### Excepción temporal propuesta para revisión — PR #87

- **Única identidad:** [GHSA-fc5q-39xc-vjpf / CVE-2026-112366](https://github.com/advisories/GHSA-fc5q-39xc-vjpf), ReDoS en `picomatch`. El advisory no ofrece versión corregida al revisar el 17/11/2026. El lockfile actual usa `picomatch@4.0.7`; las 11 alertas HIGH son este hallazgo y sus dependientes de desarrollo. Producción: cero hallazgos.
- **Alcance verificable:** opción explícita `--npm-dev-exception-lock frontend/package-lock.json` solo en la auditoría completa. Cada causa `via` debe terminar exclusivamente en ese advisory de `picomatch@4.0.7`; todos los nodos e instancias del paquete deben existir con `dev: true` en el lockfile v3. Referencias ausentes, ciclos, versiones diferentes y causas adicionales no se exceptúan. Una nueva HIGH/CRITICAL sigue bloqueando.
- **Vencimiento:** **01/12/2026 a las 00:00 UTC** (fecha exclusiva), sin renovación automática. Desde ese momento los hallazgos presentes vuelven a bloquear. Los errores de escaneo o informes contradictorios siempre bloquean.
- **Evidencia:** `npm.json` conserva cada hallazgo, severidad y marca de excepción, identidad, caducidad y cantidad exceptuada; la consola muestra esa cantidad. `npm-production.json` registra el análisis separado de producción, obligatorio y sin excepciones incluso para el mismo advisory. Ambas auditorías se ejecutan aunque falle producción; el job conserva su fallo.
- **Riesgo residual:** denegación de servicio por patrones glob maliciosos durante lint/build en Node; no se considera remediada la vulnerabilidad. Mantener las herramientas de desarrollo fuera del servicio productivo y revisar código/patrones de contribuciones no confiables.
- **Eliminación:** actualizar a versiones corregidas compatibles cuando existan, repetir auditorías completa/producción, normalizador, lint, tests y build; retirar la opción y el código/pruebas de excepción cuando no haya hallazgos derivados. No ampliar alcance ni prorrogar sin otra revisión explícita. Esta propuesta local queda pendiente de aceptación; no se ha publicado.

## DAST seguro

- FastAPI escucha únicamente en `127.0.0.1:8765` del runner de GitHub.
- `AGROSCAN_DATA_DIR` y JWT son efímeros, con `Base.metadata.create_all(engine)` sobre SQLite vacía; sin archivos reales.
- Se prueba autorización actual de SaaS-07 (`Authorization: Bearer agd_...` individual), no cabeceras `X-Device-Key` antiguas.
- ZAP se ejecuta con `zap-api-scan.py -S`; **no se dirige a producción, Vercel, una URL externa ni cámaras**.
- La evidencia de CI no acredita DAST autenticado con usuario corporativo, penetración activa, métricas de exactitud IA ni seguridad de la infraestructura desplegada.

## Restricciones y cobertura pendiente

- Los hallazgos históricos de Gitleaks anteriores al PR no se declaran eliminados: el gate impide secretos **nuevos**. La remediación del historial y rotación de credenciales requiere una actuación independiente.
- `vision/requirements.txt` incluye una dependencia Git y `vision/requirements-experiment.txt` no fija todas las versiones; el SCA automático aquí solo cubre requisitos pinneados de backend/IoT y `frontend/package-lock.json`. La cobertura SCA de modelos/visión queda pendiente de normalizar sus lockfiles o SBOM reproducible.
- Si hay vulnerabilidades reales, **no** bajar umbrales ni usar `continue-on-error`/`|| true`: tratar hallazgos y justificar ajustes en una PR separada.
- CI utiliza `actions/checkout`/`setup-*` y `upload-artifact` con SHA de referencia heredados del workflow anterior. Confirmar funcionamiento en GitHub Actions y vigencia de las imágenes de escáner en la primera ejecución.

## Cierre

1. Validar syntax (`git apply --check`, `python -m unittest`, parser YAML/Actions); publicar en rama nueva.
2. Abrir PR hacia `main`, revisar **todos** los jobs y los reportes sanitizados.
3. Comprobar resultado global, distinguiendo errores de configuración de vulnerabilidades encontradas.
4. No fusionar hasta solucionar fallos reales, con evidencia.
