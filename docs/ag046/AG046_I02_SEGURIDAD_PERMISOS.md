# AG-046 / AGROP-54 — Incremento 02 · Seguridad y permisos

**Fecha de preparación:** 2026-11-16. **Base de lectura:** `main`, commit `1d3b66b7017f7f9139a5a35521f458bf100f6a66`.

**Estado:** batería preparada y comprobada sintácticamente; **ejecución contra el repositorio local del responsable pendiente**. No se han ejecutado los tests API de FastAPI/SQLite ni la batería frontend contra el checkout real en esta preparación. El resultado de I02 debe obtenerse por `backend/audit/ag046_i02_run.py` y nunca inferirse de una inspección estática.

## 1. Alcance

Se verifican los controles `SEC-01` a `SEC-12` de `AG046_I01_CHECKLIST.md`, sin modificar la lógica de negocio de AgroScan ni reemplazar registros existentes. Se reutilizan las suites AGROP-47 (autenticación/roles), AGROP-46 (decisiones auditables), AG-056 (cola de revisión) y AGROP-53 (autorización del respaldo).

- **Autenticación:** JWT HS256, secreto de longitud mínima, claims, firma, caducidad, sesión inactiva, login y hash Argon2.
- **Autorización:** matriz de operador/revisor/administrador para usuarios, evaluaciones, decisiones, bandeja y respaldo/restore.
- **Frontend:** controles de fuente sobre el uso del JWT en memoria, cabecera `Authorization` y limpieza en logout (no son E2E de navegador).
- **Inventario de riesgos:** `POST /api/iot/measurements` actualmente sin autenticación en el código de `main`, y separación entre anotación E0/E1/E2 experimental (`require_operator`) y decisión formal AG-038 (`require_reviewer`).

## 2. Matriz de acceso esperada por el código vigente

| Operación / endpoint | Anónimo | Operador | Revisor | Administrador |
|---|---|---|---|---|
| `GET /api/auth/me` | 401 | 200 | 200 | 200 |
| `GET /api/lots`, `/api/evaluations` | 401 | 200 | 200 | 200 |
| `GET /api/images/{id}` | 401 | 200 | 200 | 200 |
| `POST /api/evaluations/{id}/review-decisions` | 401 | 403 | 201* | 201* |
| `POST /api/evaluations/{id}/cancel` | 401 | 403 | 403 | 201* |
| `GET /api/reviews/queue` | 401 | 403 | 200 | 200 |
| `GET/POST/PATCH /api/users...` | 401 | 403 | 403 | 200/201* |
| `POST /api/admin/backups` | 401 | 403 | 403 | 200* |
| `POST /api/admin/backups/restore` | 401 | 403 | 403 | 200* |
| `POST /api/evaluations/{id}/vision/quality/reviews` | 401 | Autorizado* | 403 | Autorizado* |
| `POST /api/iot/measurements` | **Aceptado actualmente** | Aceptado | Aceptado | Aceptado |

\* Condicionado a datos válidos y estado permitido. Para `quality/reviews`, la prueba I02 utiliza un expediente inexistente: **404** significa que el rol pasó la autorización, no que se creó una anotación. Para respaldo/restauración en I02 la ejecución permitida se comprueba con *mocks*, no con archivos operativos.

**Distinción funcional:** las anotaciones experimentales de calidad y las decisiones formales con bitácora no son equivalentes. No se alteran sus permisos sin validación de negocio.

## 3. Diseño de aislamiento

- Cada caso de la batería nueva crea un directorio temporal y una SQLite exclusiva. La dependencia `get_db` de FastAPI se sustituye solo durante la prueba y se restaura después.
- Las contraseñas y usuarios son exclusivamente ficticios. Los tokens se generan con una clave de pruebas suministrada al subproceso; no leer `.env` operativo ni imprimir secretos.
- Se prueba que las operaciones no autorizadas no agreguen usuarios, revisiones ni mediciones cuando el endpoint está protegido.
- Los endpoints de backups no se ejecutan realmente en las pruebas de roles; las pruebas funcionales de respaldo/rollback pertenecen a I03.
- El test IoT **demuestra el comportamiento observable actual** (escritura sin credencial). Aunque esa aserción pase, `SEC-11` permanece no conforme o condicionado a política y arquitectura de despliegue.
- Se conserva el contenido completo del `docs/ag046/` de I01. Los resultados I02 se generan en `docs/ag046/runs/`, sin sobrescribir la matriz base de I01.

## 4. Cómo ejecutar

En la raíz de `iot-fruit-classification`, PowerShell:

```powershell
# No cambia la rama y no toca datos existentes.
.\backend\.venv\Scripts\python.exe .\backend\audit\ag046_i02_run.py
if ($LASTEXITCODE -ne 0) { Write-Warning 'I02 tiene etapas fallidas o bloqueadas; revise los logs antes de continuar.' }
Get-ChildItem .\docs\ag046\runs\ -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

Requisitos: el entorno Python del backend debe tener `backend/requirements.txt` instalado y Node.js disponible. No es necesario iniciar FastAPI ni Vite para estas pruebas aisladas.

### Archivos de salida

`docs/ag046/runs/AG046_I02_YYYYMMDDTHHMMSSZ/` contiene:

- `AG046_I02_RESULTADOS.json`: fecha, etapas, resultado y casos informados.
- `AG046_I02_MATRIZ_RESULTADOS.csv`: clasificación de los controles SEC sin convertir `SEC-11/12` en aprobados.
- `AG046_I02_RESUMEN.md`: informe legible para Jira.
- Logs específicos por suite Python y comprobaciones frontend.

Conservar copia local de esas evidencias antes de limpiarlas. Revisar logs antes de publicar; **nunca subir secretos, tokens o bases de datos personales**.

## 5. Criterios de cierre

1. La batería nueva y las regresiones se ejecutan con código de salida 0 y logs fechados, sin tests omitidos por error de configuración.
2. Operador/revisor no realizan escrituras reservadas al administrador y la denegación no crea eventos.
3. Un revisor puede registrar una decisión formal sobre evidencia sintética y no cancelar una evaluación.
4. Login y JWT rechazados correctamente cuando sean inválidos/inactivos/expirados.
5. `SEC-11` y `SEC-12` permanecen **pendientes de resolución de política**, incluso si el runner finaliza correctamente. La seguridad global de AG-046 no se marca aprobada con esos riesgos abiertos.
6. No se afirma validación de hardware, penetración externa, multiserver, ni control de producción.

## 6. Trazabilidad de casos

| Control I01 | Nuevo test / suite | Alcance |
|---|---|---|
| SEC-01 | `test_sec01_rechaza_secreto_corto_y_algoritmo_no_autorizado` | Importación con variables inválidas |
| SEC-02 | `test_sec02_tokens_invalidos_y_requisitos_de_claims` | JWT 401 |
| SEC-03 | `test_sec03_login_*` | Login, Argon2, cuenta inactiva |
| SEC-04 | `frontend/tests/ag046-i02-token-security.test.mjs` | Lectura estática de sesión JWT |
| SEC-05 | `test_sec05_rutas_protegidas_requieren_token_sin_modificaciones` | Endpoints de lectura 401 |
| SEC-06 | `test_sec06_operador_no_puede_corregir_anular_ni_decidir` | Denegación y no mutación |
| SEC-07 | `test_sec07_revisor_registra_decision_real_y_no_puede_anular` | Revisor y evento rastreable |
| SEC-08 | `test_sec08_*` | CRUD/roles de usuarios sintéticos |
| SEC-09 | `test_sec09_*` | RBAC backup/restore con mocks |
| SEC-10 | `test_sec10_bandeja_acceso_por_rol` | Cola de revisión |
| SEC-11 | `test_sec11_iot_sin_credencial_dispositivo_observacion_no_aprobacion` | Evidencia de excepción de seguridad actual |
| SEC-12 | `test_sec12_permisos_distintos_para_anotacion_y_decision_formal` | Política por acordar |

**Base del hallazgo:** `AG046_I01_REGISTRO_HALLAZGOS.md` (H01 y H03). No crear un bug como cerrado ni poner el ticket en Done hasta que la política aplicable quede documentada y se compruebe.
