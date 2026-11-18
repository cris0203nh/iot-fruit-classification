# Etapa 07 — Validación final y expediente de evidencias CI/CD

**Base:** `main` tras PR #89, merge `8d3a60433cec09ed9b804b99b87566bb9baa8f20`.
**Alcance:** validar automatización del repositorio. No certifica hardware, despliegue público, ni precisión E0/E1/E2.

## Evidencia real obtenida de GitHub Actions

| Elemento | Evidencia comprobada |
|---|---|
| PR #89 | https://github.com/cris0203nh/iot-fruit-classification/pull/89 |
| CI de PR #89 | https://github.com/cris0203nh/iot-fruit-classification/actions/runs/44227059987 |
| Resultado del run | success, 15 jobs terminados con success |
| Artefacto original | `agroscan-ci-global` (GitHub artifact ID 14394225173) |
| JSON conservado | `docs/ci/evidencias/PR89_ci-global.json` |
| Contexto de artefacto | `run_id=44227059987`, `event=pull_request`, SHA de ref de ejecución `f914864826b9fe8334149fd2ea8a91e3d0b45dc3` |
| Decisión | `approved`, 6 módulos seleccionados, 0 omisiones, 0 incumplimientos |
| SHA-256 JSON normalizado | `1cbf9f69823077b11569cf6d7ba93af16a1c910abc10b13bf2bb146600dde35b` |

El SHA del reporte identifica la ref de ejecución utilizada por GitHub Actions y **no** debe confundirse
con el commit de la rama `main` fusionada. El JSON se conserva por trazabilidad; su contrato
se comprueba por `scripts/ci/verify_evidence.py` sin pretender que la validación local autentica
por sí sola la procedencia de un archivo. La procedencia exige cotejar el artefacto con GitHub.

También existe evidencia real de bloqueo: en la ejecución
https://github.com/cris0203nh/iot-fruit-classification/actions/runs/44216492637
los análisis Python/npm y el gate final fallaron antes de remediar dependencias.
No confundir este hecho con una prueba de protección administrativa de `main`.

## Protocolo de aceptación final

1. **Caso A — CI completo:** PR que cambie scripts/workflows debe seleccionar todos los módulos.
   Verificar jobs backend, frontend, IoT (2), visión, integración, DAST, seguridad (5), selección,
   preparación y `CI - validación global`. Comprobar `agroscan-ci-global`.
2. **Caso B — Solo documentación:** **después de fusionar esta etapa**, abrir un PR nuevo que
   cambie solo `docs/ci/ETAPA07_VALIDACION_FINAL.md` (sin modificar otros archivos).
   `backend`, `frontend`, `iot`, `vision`, `integracion`, `dast` deben ser `skipped` previstos;
   `preparacion`, `cambios`, `seguridad` y el gate global deben aprobar.
   Descargar el JSON y confirmar seis omisiones previstas. No declarar validado antes de ejecutar.
3. **Caso C — Falla controlada:** las pruebas `scripts/ci/test_*` incluyen fallos simulados
   de un módulo, de seguridad, cancelación, selección inválida y omisiones indebidas.
   Para demostrar **bloqueo de fusión** en GitHub, se necesita ruleset activo sobre `main`
   y un PR de prueba con fallo deliberado en una rama de ensayo. No fusionar ese PR ni
   conservar el cambio de fallo. El resultado debe ser gate rojo y Merge bloqueado.
4. **Caso D — Reporte:** verificar que `CI - validación global` publica resumen y
   `agroscan-ci-global` sanitizado. `verify_evidence.py` devuelve código 0 para reporte
   coherente y 1 ante alteraciones de campos, estados o decisiones.
5. **Caso E — Seguridad residual:** conservar la excepción `picomatch` con vencimiento
   **01/12/2026 00:00 UTC**; el gate verde no elimina dicho riesgo ni los pendientes de
   SCA de visión y saneamiento histórico de Gitleaks.

## Protección de rama `main` — configuración administrativa pendiente de comprobación

En Settings → Rules → Rulesets, crear una regla **Active** dirigida a `main`, exigir PR y
el check exacto **`CI - validación global`** como requerido, si la cuenta y los permisos
lo permiten. Bloquear force-push. No exigir jobs selectivos susceptibles de `skipped`.
La consulta de rulesets visibles devolvió lista vacía, y la lectura de branch protection
tradicional devolvió **403** para la conexión disponible. No se afirma que la protección
esté activa. **Sin regla activa, los checks rojos no garantizan que GitHub impida el merge**.

## Ejecutar pruebas locales

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s scripts/ci -p 'test_*.py' -v
.\backend\.venv\Scripts\python.exe scripts/ci/acceptance_matrix.py --output "$env:TEMP\agroscan-e07-local-matrix.json"
.\backend\.venv\Scripts\python.exe scripts/ci/verify_evidence.py --file docs/ci/evidencias/PR89_ci-global.json
```

El archivo temporal `agroscan-e07-local-matrix.json` es una **simulación local** de 10 escenarios
de selección y gate. Nunca se presentará como un run real. Guardarlo fuera del commit.

## Capturas mínimas para presentación

- PR #89 con checks aprobados y enlace al run real.
- Diagrama de jobs conectados del run completo (captura sin datos privados).
- Pestaña Artifacts con `agroscan-ci-global`, más su JSON aprobado.
- PR separado de documentación con `skipped` justificados y gate verde (**pendiente**).
- PR de fallo controlado + indicación del bloqueo de merge por ruleset (**pendiente**).

## Criterio de cierre

Etapa 07 completa solo cuando: CI completo aprobado, PR documental real validado,
prueba de bloqueo de merge con protección activa confirmada (o limitación reportada
explícitamente), evidencia JSON comprobable y documentación actualizada.
