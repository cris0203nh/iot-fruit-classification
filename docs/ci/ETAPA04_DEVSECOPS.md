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
| npm audit | Lockfile del frontend | HIGH o CRITICAL, o error operativo |
| Gitleaks | Commits introducidos respecto a SHA base PR/push | Cualquier secreto detectado, o error operativo |
| ZAP | OpenAPI de FastAPI local; `-S` **sin escaneo activo** | HIGH o CRITICAL, o error operativo |

El repositorio tenía un DevSecOps anterior en `security/devsecops-hardening`. Se reaprovechan herramientas, el principio de sanitización de resultados y los umbrales; **no** se fusiona esa rama desactualizada ni su código productivo.

Los JSON crudos de escáneres (Gitleaks, ZAP y auditorías) se eliminan. Solo se conservan informes normalizados durante 7 días. Los reportes no incluyen cuerpos HTTP, URL con parámetros, contraseñas ni coincidencias de secretos. Mantenerlos en la revisión de acceso restringido del repositorio.

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
