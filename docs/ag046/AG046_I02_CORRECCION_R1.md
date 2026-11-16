# AG-046 — Incremento 02 · Correccion R1 de pruebas y ejecutor

**Fecha del diagnóstico:** 2026-11-16. **Base:** logs locales comunicados por el equipo.

## Fallos de la primera ejecución

1. **Prueba `SEC-02`:** 13 de 14 casos pasaron. El token de entrada `un.jwt.inválido` contiene un carácter no ASCII. La librería HTTPX no construye la cabecera `Authorization`, así que FastAPI jamás recibe la petición. Se sustituye por `un.jwt.invalido`, que es igualmente inválido pero se puede enviar con HTTPX. No se cambia `app/security.py`.
2. **Regresión AGROP-47:** 21 de 23 pruebas pasaron. Dos pruebas con perfil revisor/administrador esperan HTTP 201 al registrar una revisión genérica en una evaluación **sin fotografía**. La política actual de AG-056 exige evidencia conservada y devuelve 409. Se actualiza el fixture compartido para crear una evidencia sintética de una sola vista en un directorio temporal. Las comprobaciones originales **201/403/401** permanecen. Se añade una prueba negativa que confirma **409 si desaparece el archivo**. No se modifica `app/routers/evaluations.py`.
3. **Frontend `SEC-04`:** 4 de 4 pruebas pasaron cuando Node se ejecutó expresamente en modo TAP. El ejecutor original buscaba `# tests N` pero Node imprimía el reporte resumido con símbolos `ℹ`. Se fuerza `--test-reporter=tap`, sin modificar las aserciones ni el código React.

## Seguridad y validez

- La base usada en pruebas continúa siendo SQLite temporal, distinta de `backend/data/agroscan.db`.
- `HTTP 409` al faltar evidencia **se conserva** y se verifica explícitamente. No se reducen controles de autorización.
- Los resultados 13/14, 21/23 y 4/4 son los de la ejecución informada; **este parche aún requiere validación de ejecución local** y no acredita éxito por sí solo.
- Los criterios **SEC-11** (ingesta IoT sin autenticación de dispositivo), **SEC-12** (política de anotación experimental) y la prueba de sesión real en navegador siguen pendientes de decisión o evidencia.
- Los logs originales `docs/ag046/runs/AG046_I02_20261116T130747_984670Z/` no deben borrarse ni sobrescribirse. El ejecutor creará una carpeta nueva en la siguiente ejecución.

## Repetición

```powershell
.\backend\.venv\Scripts\python.exe .\backend\audit\ag046_i02_run.py
if ($LASTEXITCODE -ne 0) { Write-Warning "Revisar los logs de la nueva ejecución" }
$run = Get-ChildItem .\docs\ag046\runs\ -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content -Encoding UTF8 (Join-Path $run.FullName "AG046_I02_RESUMEN.md")
```

**Criterio de salida R1:** las seis etapas automatizadas deben pasar y producir recuentos observables; SEC-11/12 siguen sin acreditarse aunque todas las pruebas técnicas pasen.
