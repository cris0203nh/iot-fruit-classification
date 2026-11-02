# AGROP-27 — Vistas adicionales vinculadas a la misma evaluación

## Alcance de frontend

- Recuperar las imágenes persistidas de la evaluación antes de habilitar una nueva toma.
- Mantener el mismo identificador `E-...` para todas las fotografías de una pieza.
- Etiquetar `vista-1`, `vista-2`, `vista-3` sucesivamente y enviar cada etiqueta al endpoint existente.
- Mostrar las imágenes y sus identificadores `I-...` en la pantalla de captura.
- Solicitar el giro **manual** de la misma fruta antes de tomar otra perspectiva.
- Conservar la vista previa, repetición y descarte **antes de guardar** de AGROP-26.
- No iniciar una nueva evaluación ni realizar clasificación ni control automático del giro.

El historial ya muestra `evidence[]` en el detalle y el contador de imágenes en la ficha. No se modifican modelos ni migraciones.

## Prueba funcional pendiente (no declarar realizada antes de ejecutarla)

1. Actualizar el código desde `main`, instalar y arrancar backend y frontend con las dependencias actuales.
2. **Verificar autenticación AGROP-47**: el backend exige permisos de operador para subir imágenes y acceso autenticado para consultar la evaluación y sus imágenes. Si no se puede iniciar sesión desde React, coordinar con los responsables de AGROP-47. No desactivar controles de seguridad.
3. Registrar una pieza DEMO en un lote abierto y anotar el identificador real de evaluación.
4. Capturar o seleccionar una fotografía frontal y guardarla como `vista-1`. Anotar `I-...`.
5. Girar manualmente **la misma** fruta. Capturar la vista lateral y guardar como `vista-2`, sin crear otra evaluación.
6. Verificar que ambas imágenes aparezcan juntas con el mismo `E-...` en la pantalla de captura y en Historial / Detalle.
7. Volver a consultar el detalle y comprobar dos imágenes e identificadores diferentes. No atribuir calidad, pesaje o clasificación física si no se ha comprobado.
8. Rechazar una fotografía antes del envío y comprobar que no aumenta el contador del backend.

### Evidencia para Jira

Capturas o video de: identificación de la pieza, giro manual, vista 1 y vista 2 guardadas, detalle de evaluación con ambas imágenes y resultados de pruebas. Separar la prueba desde escritorio de la captura directa desde teléfono, que requiere validación con Fernando.

**Nota de integración:** El commit base consultado fue `6b8e31c` de `main` el 1 de noviembre de 2026. Verificar si hay commits posteriores antes de aplicar el parche.
