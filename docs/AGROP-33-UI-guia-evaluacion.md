# AGROP-33 [AG-025] — Interfaz de evaluación por pasos

## Alcance

Interfaz de operador para **identificar pieza → colocar y pesar → capturar fotos → confirmar adquisición → retirar**. Reutiliza la gestión de lotes y piezas (AGROP-30), el estado de pesaje IoT (AGROP-22/24/31), las fotografías (AGROP-26/27/32) y los permisos JWT (AGROP-47). No altera sus endpoints ni la base de datos.

## Funcionamiento

1. **Identificar:** seleccionar producto, lote abierto y código de pieza. La aplicación utiliza `POST /api/evaluations` y presenta el ID devuelto.
2. **Colocar y pesar:** muestra el estado real de `GET /api/iot/status`. El botón de peso inicial usa `POST /api/evaluations/{id}/weight/pre`; únicamente un HTTP exitoso permite indicar peso confirmado. Si el sensor no está disponible, el operador puede continuar a las fotos, **con peso pendiente**.
3. **Fotografías:** reutiliza el módulo RGB y sus reintentos idempotentes. El contador se actualiza después de cargar el detalle persistido o guardar una imagen confirmada por la API. No permite continuar sin al menos una foto confirmada.
4. **Confirmación:** muestra el ID, las fotos y ambos pesos. Si existe peso inicial, permite solicitar `POST /api/evaluations/{id}/weight/post`. Los errores del backend se muestran; no se rellenan valores sintéticos. Se permite continuar al retiro con pesaje pendiente y se identifica como adquisición parcial.
5. **Retiro:** requiere que el operador marque la confirmación manual de retiro para iniciar otra pieza. Es un estado **solo de UI**: el backend no tiene endpoint de retiro ni de cierre global de evaluación.

## Límites honestos

- La guía no escribe el estado `completed` en SQLite, no inventa una clasificación y no afirma que se haya medido físicamente un peso.
- La confirmación de colocación/giro/retiro es declarativa por parte del operador y no prueba sensores de presencia de fruta.
- Las confirmaciones de peso en el frontend corresponden a la sesión de la pantalla. La API pública de detalle de evaluación no expone ambos registros parciales; al recargar se debe consultar backend antes de asumirlos.
- El backend de pesaje valida frescura, estabilidad, calibración, tara y secuencia. Un `409` es un rechazo real, no un éxito.
- No se cambió el contrato de seguridad JWT ni la política de evidencia RGB.

## Validaciones propuestas en Windows

Desde la raíz del proyecto, en una rama limpia basada en `origin/main`:

```powershell
git apply --check PATCH_AGROP33_01_FLUJO_EVALUACION.patch
git apply PATCH_AGROP33_01_FLUJO_EVALUACION.patch
cd frontend
npm test
npm run lint
npm run build
```

Para Jira, captar: paso 1 con lote/pieza, estado del sensor (con o sin lectura), vista RGB, guardado con ID real y paso de retiro mostrando adquisición parcial/confirmada según corresponda. No adjuntar credenciales ni tokens.
