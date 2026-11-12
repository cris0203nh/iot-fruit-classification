# AG-054 / AGROP-66 — Incremento 01: geometría YOLOE por evidencia RGB

**Base:** AG-053 fusionado en `main`. **Estado:** requiere validación en el repositorio local y con YOLOE real antes de cerrar Jira.

## Alcance implementado

1. Superposición del recuadro amarillo y máscara verde sobre la fotografía preliminar de AG-053.
2. Al guardar una fotografía de una evaluación, AgroScan solicita a FastAPI una inferencia YOLOE y registra una instantánea geométrica por evidencia RGB. Se admite análisis manual por foto cuando esté pendiente.
3. Endpoint autenticado `POST /api/evaluations/{evaluation_id}/vision/geometry/{image_id}`: obtiene el original por referencia, comprueba longitud, calcula SHA-256, valida correspondencia con la evaluación, invoca el mismo detector de AG-053 y persiste la geometría por imagen/versión. Repetir la solicitud con la misma evidencia y versión devuelve el resultado original (sin nueva inferencia).
4. Endpoint `GET /api/evaluations/{evaluation_id}/vision/geometry`: solo lectura, consulta de las instantáneas originales por foto para el Historial y Trazabilidad.
5. Superposición y métricas del análisis persistido en adquisición, detalle del Historial y Trazabilidad. Los registros sin medición conservan su fotografía original.
6. Nueva migración Alembic `e054a1b2c3d4` que depende de `d50b9a0e53aa`. No altera registros preexistentes.

## Atributos y unidades

- Ancho y alto proyectados del polígono, en **px**.
- Eje mayor y menor de rectángulo mínimo orientado, en **px**.
- Área aproximada del contorno YOLOE, en **px²**; perímetro aproximado, en **px**.
- Relación de ejes y fracción del área del fotograma.
- Producto detectado, confianza, máscara, caja, versión de modelo, reglas, SHA-256 del original, identificadores de evaluación/imagen y fecha.

**No medimos centímetros, diámetro físico, volumen, peso ni tamaño real.** Para unidades físicas se requiere referencia de escala/calibración verificada, plano de referencia y control de perspectiva. La proyección es bidimensional y no estima la profundidad del fruto.

**No predecimos E0/E1/E2 ni defectos:** será la historia AG-055, condicionada a datos reales etiquetados y validación independiente. Un resultado `needs_review` es incertidumbre geométrica, no una decisión de calidad ni un cambio de estado de evaluación.

## Reglas de aceptación de la geometría

Publicar métricas solamente si el detector encuentra exactamente **una** fruta conocida, compatible con el producto del lote, confianza mínima 0,40 y una máscara válida con superficie y límites finitos. En otros casos se persiste el motivo (`sin_deteccion`, `varias_frutas`, `producto_distinto_al_lote`, `confianza_insuficiente`, `segmentacion_no_disponible`, `segmentacion_invalida`) sin medición, dejando la foto original intacta. Un fallo al cargar YOLOE retorna HTTP 503 y no inventa datos.

## Seguridad y trazabilidad

- El servidor comprueba permisos: solo `operador`/`administrador` pueden activar análisis; todos los roles autenticados pueden consultar.
- Se comprueba que `I-...` pertenezca a la evaluación indicada, la ruta permanezca dentro de `DATA_DIR` y el tamaño coincida con el registrado.
- El hash SHA-256 y un índice único por evidencia/hash/modelo/reglas permiten consulta idempotente y trazabilidad de versiones.
- El análisis no reemplaza ni modifica el archivo original, el peso, la pieza, lote, etiqueta humana o revisiones previas.
- No se informa como «medición confirmada» si no existe inferencia y máscara válidas.

## Plan de verificación local

1. Verificar la rama desde `origin/main` después de fusionar AG-053. No mezclar AG-034/AG-036 u otros cambios sin relación.
2. Instalar AG-054 sin respaldos auxiliares (el instalador no toca SQLite) y ejecutar `git diff --check`.
3. En `backend`, ejecutar `python -m unittest discover -s tests -p 'test_ag054_*.py' -v`.
4. En `frontend`, ejecutar `npm test` y `npm run build`.
5. Detener FastAPI y generar **un único archivo de respaldo SQLite** (no directorios); después `python -m alembic current` y `python -m alembic upgrade head` si la versión es `d50b9a0e53aa`.
6. Probar **con fotografía real** de mango y tomate: confirmar producto, máscara superpuesta y caja en el inicio AG-053. Registrar lote y pieza; guardar dos vistas; comprobar métricas por evidencia en Captura/Historial/Trazabilidad.
7. Repetir POST de una imagen: confirmar que se devuelve el mismo registro e identificador (no crea otra medición). Revisar manejo de foto ajena, dos frutas, ausencia YOLOE y token de usuario.
8. Registrar capturas de pantalla y métricas de ambas frutas para Jira AGROP-66; no marcar como validación real de dimensión física.

## Limitaciones conocidas

- YOLOE produce una máscara **2D** y el módulo estima métricas mediante contorno polygonal reducido. No constituye metrología física calibrada.
- Cada fotografía guardada necesita inferencia una vez. Si el proceso falla, permanece la imagen original y puede reanalizarse, pero no se inventa geometría.
- No se realizan inferencias en cada visita a Historial o Trazabilidad: ambas pantallas leen registros persistidos.
- Aún faltan ensayos de medición real, desempeño con cámaras y hardware físico, y clasificación E0/E1/E2 validada.
