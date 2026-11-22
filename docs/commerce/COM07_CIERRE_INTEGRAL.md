# COM-07 — Cierre comercial integral

**Fecha:** 20/11/2026 (America/Lima). **Dictamen: PARCIAL.**

El recorrido comercial automatizado aprobó sobre SQLite desechable migrada a `c015imagekey`, sin cobros ni conexiones SMTP/OAuth reales. No equivale a E2E visual: no hay navegador disponible. QA principal permanece deliberadamente en `c014onboarding`, sin modificaciones de datos; requiere aplicar la migración correctiva antes de reiniciarlo o validar fotografías. No se declara preparación comercial/productiva.

## Matriz de evidencia

| Escenario | Resultado | Evidencia ejecutada / alcance |
|---|---|---|
| Landing → catálogo → selección y formulario públicos | PARCIAL | F: rutas/componentes SSR, CTA con plan y select; Q: catálogo real mediante cliente TS y proxy. Clicks/renderizado en navegador no ejecutados |
| Solicitud sin sesión, recibo pendiente y repetición | APROBADO API | Q: solicitud nueva en copia, recibo sin contactos, misma referencia ante reintento; B: validación, límites y ausencia de aprovisionamiento |
| Propietario: aprobar/rechazar, asociación e idempotencia | APROBADO API | Q: dos aprobaciones concurrentes producen una empresa A; B aprobada y otra solicitud rechazada sin empresa. B: conflictos, rollback y plan inactivo |
| Invitación inicial, revocación, reemisión y aceptación | APROBADO API | Q: rol/correo fijados, token solo en emisión, enlace revocado 410, cuenta elegida por cliente y login A/B; B: caducidad, consumo único y concurrencia |
| Primera orden rechazada/cancelada | APROBADO API | Q: suscripción nula y etapa `awaiting_demo_order` tras ambos resultados |
| Primera orden DEMO aprobada | APROBADO API | Q: tres confirmaciones concurrentes, una activación, referencias solicitud/invitación/orden/suscripción y `completed` |
| Renovación, cambio, cancelación e historial | APROBADO API | Q: renovación extiende vigencia una vez; cambio conserva plan hasta aprobar; cancelación inmediata repetible. Siete órdenes y siete transacciones adicionales solo en copia |
| Caducidad y gracia | APROBADO API/tiempo simulado | Q: orden de >24 h devuelve 409; suscripción expirada con gracia a +1 día, sin gracia a +7/+8 días; operación permitida. B: calendario y periodos |
| Propietario: estados, empresas y totales DEMO consistentes | APROBADO API | Q: métricas por delta respecto del historial previo, referencias y etapas verificadas; F: componentes del propietario. No ingresos reales |
| Operador/revisor: operar, no contratar/renovar/cancelar | APROBADO API | Q: consultas operativas permitidas; comercio devuelve 403, y escritura de lotes del revisor 403, probada en copia |
| A/B e IDs empresariales manipulados | APROBADO API | Q: dos empresas nuevas con administradores independientes; IDs ajenos 403/404. B: FK compuestas, permisos revocados, precios alterados y rollback |
| Deep links, invitaciones en fragmento y cierre de sesión | PARCIAL | F: contratos de rutas/AuthGate/sesión y SSR. Q: autenticación real por rol; clic de logout/navegación en navegador pendiente |
| Responsive, teclado, foco y errores visuales | PENDIENTE | F verifica contratos/semántica/CSS; no acredita vistas desktop/móvil. V: inventario vacío y `Browser is not available: iab` |
| Migraciones y conservación | APROBADO EN COPIAS | B/G: cadena real desde vacía, roundtrips y guardas; c015 preserva IDs/filas/foto sintética y aplica unicidad. Q/D: QA origen sin cambios, integridad `ok`, cero FK inválidas |
| Esquema de QA principal | BLOQUEADO PARA ACTIVACIÓN | Sigue en c014, donde falta `images.idempotency_key`. Corrección probada solo en temporal/copia; no se migró QA principal ni base histórica |

## Pruebas exactas

| Ejecución final | Resultado |
|---|---|
| Backend completo (`backend/tests/test_*.py`), checkout de código y SQLite/JWT/archivos temporales | **534 ejecutadas: 531 aprobadas, 3 omitidas; 0 fallos/errores** |
| Frontend (`npm test --prefix frontend`) | **213 ejecutadas: 212 aprobadas, 1 omitida; 0 fallos** |
| QA (`python -m unittest discover -s tests -p test_agroscan_qa.py -v`) | **5/5 aprobadas**, incluida regresión con historial comercial, lote/evaluación y fotografía de bytes sintéticos preexistentes |
| Lint y build frontend | Ambos **exit 0**; advertencia de bundle JS >500 kB (656,66 kB minificado) |
| `tools/agroscan_qa.ps1 -Action verify` | **exit 0**: cliente TypeScript contra proxy QA de solo lectura + recorrido API completo sobre copia desechable actualizada a c015 |

Omisiones, sin ocultarlas: backend `test_ag055_exploratory...real_photographs` y `test_ag055_pilot117...real_photo` requieren evidencia/modelos reales; `test_saas07_iot_storage...enlaces_de_archivo_no_se_siguen` no pudo ejecutar symlinks en Windows. Frontend omite la comparación con evidencia de inferencia real (`commercial-classification`). No se añadieron `skip` ni se desactivaron controles.

## Incidencias reproducidas y corregidas

1. **Verificador obsoleto:** fallaba con `7 != 0` al exigir cero órdenes en QA. También suponía ausencia de suscripciones y operaciones. Se sustituyeron esas suposiciones por comprobaciones de aislamiento/consistencia; todas las mutaciones de prueba pasan a la copia. Regresión ejecutada con historial e imagen sintética conservados. No se vació QA para superar la prueba.
2. **Deriva ORM/Alembic:** una base creada hasta c014 falló al insertar `Image`: `table images has no column named idempotency_key`. La suite con `Base.metadata.create_all` no detectaba esa carencia. Nueva **`c015imagekey`** añade la columna nullable y la unicidad `(evaluation_id, idempotency_key)`, ya exigidas por la API. No reescribe migraciones anteriores ni cambia modelos/algoritmos. Duplicados previos bloquean la migración sin borrar datos; downgrade con claves registradas se rechaza. Tres regresiones sobre Alembic real cubren conservación, unicidad, rollback y reversión segura.

El verificador puede **leer** QA c014 para actualizar únicamente una copia. El arranque normal exige c015; no hay fallback ni migración automática. **Pendiente:** respaldo y aplicación explícita/revisada de c015 en QA principal antes de reiniciarlo; producción/base histórica fuera de esta ejecución.

## Evidencias y reproducción local

- **B:** `.agroscan-checkpoints/commercial/com07-backend-final.{json,log}`. Primera pasada previa al arreglo: 531 tests, sin fallos; la regresión sobre esquema migrado descubrió después la deriva indicada.
- **F:** `.agroscan-qa/com07/frontend-results.json`, `frontend.log`, `lint.log`, `build.log`.
- **Q/G:** `.agroscan-qa/com07/verify-final.log`, `.agroscan-qa/commerce-verification.json`, `.agroscan-qa/com07/qa-tests.log`.
- **D:** `.agroscan-qa/com07/conservation.json`: SHA-256 de base histórica igual al baseline anterior; no conexión SQL de validación contra ella. QA origen: fingerprint por tabla idéntico antes/después de la copia. La QA real contiene cero fotografías; no se presenta ese conteo como validación de cámara ni de imágenes reales.
- **V:** `.agroscan-qa/com07/browser.json`: desktop/móvil no ejecutados.

Estas evidencias locales están ignoradas por Git. No publicar bases, DPAPI, tokens ni archivos privados. Los componentes UX/UI y sus cambios locales no se editaron en este cierre.

```powershell
# Comandos ejecutados desde la raíz; el runner local aislado está ignorado por Git.
backend/.venv/Scripts/python.exe .agroscan-checkpoints/commercial/run_com07.py com07-backend-final
npm test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
backend/.venv/Scripts/python.exe -m unittest discover -s tests -p test_agroscan_qa.py -v
$env:AGROSCAN_SMTP_ENABLED = 'false'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/agroscan_qa.ps1 -Action verify
```

## Pendientes externos y salida

**PENDIENTES EXTERNOS, no validados:** SMTP real/entrega en buzón; OAuth Google real (solo RSA/JWKS sintéticos en pruebas); ESP32/cámara/báscula físicos; despliegue productivo; exactitud experimental E0/E1/E2. También pendiente ejecutar la prueba de symlinks en un entorno que lo permita.

Para aprobar el cierre: activar/revisar c015 sobre QA autorizada con respaldo; ejecutar y conservar evidencia de navegador real desktop y móvil para el recorrido público/privado, aceptación, checkout, errores y logout; resolver la cobertura de symlinks. Los externos requieren su validación propia antes de cualquier declaración comercial/productiva. No se hicieron commit, push, merge, cambios de IA, firmware ni CI/CD.
