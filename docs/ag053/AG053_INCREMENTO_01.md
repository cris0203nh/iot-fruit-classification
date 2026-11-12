# AG-053 — Incremento 01: identificación YOLOE previa y registro automático

**Historia:** «Como operador, quiero que AgroScan identifique automáticamente la fruta y registre su pieza para reducir el ingreso manual».

## Cambios

- Nueva ruta `POST /api/vision/precheck`: recibe un JPG/PNG temporal; ejecuta el **YOLOE real del backend**, con los pesos/prompts actuales, y devuelve producto, confianza, caja y máscara. Si no hay exactamente un candidato válido con confianza ≥0.40 y máscara poligonal, **no entrega token** ni inventa un producto.
- Nueva ruta `POST /api/evaluations/auto`: solo acepta un token autorizado y vigente de la detección anterior, comprueba operador y lote abierto del producto, reserva un código sucesivo `P-000001`, `P-000002`... **por lote**, y crea `Piece` + `Evaluation` en una única transacción SQLite. Repetir el mismo token devuelve la evaluación original (idempotencia).
- Nueva tabla `vision_prechecks` creada por migración Alembic **aditiva**. No se borra la base de datos ni se reescriben evaluaciones históricas.
- Nueva experiencia en `Nueva evaluación`: elegir fotografía local o fotograma de cámara, analizar YOLOE primero, escoger lote compatible y registrar sin teclear producto ni pieza. La fotografía preliminar se intenta conservar como `vista-1` de la evaluación; si falla la subida, se informa sin duplicar la pieza.
- Registro manual anterior preservado como alternativa explícita ante indisponibilidad o incertidumbre. La ruta antigua `POST /api/evaluations` se mantiene.
- Se conserva la adquisición guiada de **cinco etapas** en este incremento: solo cambia el paso 1 a «Detectar y registrar pieza». No se altera la regla AG-043 de **dos fotografías** ni el pesaje físico verificado. La reestructuración global a seis etapas queda para integración posterior si se aprueba y prueba.

## Límites y condiciones de aceptación

- **NO** incluye clasificación automática E0/E1/E2 ni mediciones en centímetros. YOLOE detecta clase, localiza y segmenta; no evalúa calidad.
- Los tests HTTP emplean predicciones **controladas/mocks solo para verificar contratos**, no prueban exactitud del modelo. Probar YOLOE real requiere ejecutar la aplicación con fotografías de frutas representativas y confirmar la detección visual.
- Un código autogenerado no demuestra por sí mismo identidad física de la fruta. El operador debe colocar una sola pieza y verificar la correspondencia del lote.
- Sin los pesos/embeddings y dependencias Ultralytics, `/api/vision/precheck` responde HTTP 503: **no** simula una predicción.
- La selección de imagen en la interfaz está diseñada para operar sin cámara/ESP32; la adquisición completa seguirá limitada hasta disponer de pesajes verificados.
- El código autogenerado es **por lote**. Las piezas manuales con otros formatos de referencia no se modifican. Las manuales de formato `P-<número>` se incluyen al calcular el siguiente correlativo.
- El token de detección expira en 15 minutos si no se utilizó. Un token ya usado solo puede consultar/reintentar **la misma** evaluación por el mismo usuario y lote.

## Instalación segura en Windows

1. Usar una rama propia que contenga AG-043: `feature/AG053-identificacion-automatica`. No aplicar sobre un `main` que aún no haya recibido AG-043.
2. Respaldar `backend/data/agroscan.db` **antes** de Alembic y cerrar procesos FastAPI que la utilicen.
3. Desde la raíz del repositorio, ejecutar el instalador con `--check` y después con `--apply`; el instalador hace copia de seguridad de los archivos que edita, sin alterar la base de datos.
4. Ejecutar en `backend`: `python -m alembic current` y comprobar que el estado coincide con las migraciones del proyecto; luego `python -m alembic upgrade head`. La nueva revisión es `d50b9a0e53aa`, hija de `b38c99a10246`. Si el estado previo no es el esperado, detenerse y revisar, **no borrar ni aplicar stamp a ciegas**.
5. Ejecutar pruebas backend `python -m unittest discover -s tests -p "test_ag053_*.py" -v`, regresión AG-043 y `npm test`/`npm run build` en frontend.
6. Levantar backend y frontend; autenticar como operador y abrir `Nueva evaluación`. Probar mango, tomate, ausencia de fruta, varias frutas y lote incompatible. Confirmar que el paso 2 usa la misma evaluación sin duplicaciones.

## Evidencia para Jira

- Resultados HTTP y SQLite de `test_ag053_auto_registration.py` (inferencia simulada para contratos), con revisión de permisos, idempotencia, lote incompatible y concurrencia.
- Capturas de la interfaz y registro real del servidor al procesar imágenes con YOLOE.
- `GET /api/evaluations/{id}` mostrando código de pieza autogenerado y producto consistente.
- Resultados de `npm test`, `npm run build` y pruebas existentes AG-043.

**No cerrar la historia solo con las pruebas unitarias:** obtener evidencia real de al menos una fotografía de mango y una de tomate, y comprobar la navegación completa antes de marcarla Done.
