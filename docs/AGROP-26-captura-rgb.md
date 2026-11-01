# AGROP-26 [AG-018] — Captura, repetición y vinculación de una fotografía RGB

## Alcance de la historia

Requisito: obtener una fotografía RGB legible, permitir repetir la toma antes de confirmarla y asociar la fotografía válida al identificador de una evaluación en proceso. Dependencia documental: AGROP-25 [AG-017], informe de Fernando, versión 1.1, 01/11/2026. La alternativa principal es teléfono sostenido a mano; la webcam queda como opción de archivos de prueba. No se exige soporte fijo.

No cubre múltiples vistas (AGROP-27), detección automática de defectos/calidad (AGROP-28), calibración del pesaje, ni clasificación. Una fotografía guardada no completa una evaluación.

## Implementación

- React: tras crear una evaluación real `E-...`, sección Cámara RGB con botones «Tomar fotografía» (captura móvil) y «Elegir JPG/PNG», vista previa, «Repetir toma», «Descartar» y «Guardar en evaluación».
- No se envía ninguna foto hasta confirmar. Repetir la toma antes de guardar no duplica evidencia en SQLite.
- Cliente API: `POST /api/evaluations/{id}/images`, multipart (`file`, `view=vista-1`). Valida estructura de respuesta con `I-...` y ruta emitida por FastAPI. La foto se consulta desde `/api/images/{id}`.
- Backend: permite asociar una imagen a una evaluación **en proceso** aun sin pesaje físico inicial, para comprobar AGROP-26 sin bloquearse por AGROP-21/23. No altera los requisitos de pesaje ni habilita finalización.
- Límites: JPG/PNG declarados y cabecera reconocible, archivo no vacío, hasta 5 MiB; otros formatos como HEIC se rechazan con explicación. La validez técnica del archivo no demuestra legibilidad, enfoque ni calidad para un clasificador.
- Entorno de desarrollo: `vite.config.ts` proxifica `/api` al FastAPI local, y el cliente usa rutas relativas si no existe `VITE_API_BASE_URL`. Permite acceder desde un teléfono conectado a la misma LAN mediante la IP del equipo Vite. En producción configurar proxy `/api` o `VITE_API_BASE_URL` de forma acorde con el despliegue.

## Validación automatizada

Desde `backend`:

```cmd
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_agrop26_capture.py" -v
```

Desde `frontend`:

```cmd
npm test
npm run lint
npm run build
```

Casos AGROP-26: vinculación a evaluación existente, recuperación por URL y listado de evidencias, rechazo de evaluación desconocida, evaluación cerrada, archivo vacío, contenido suplantado, tamaño excesivo; validación de MIME y multipart desde frontend. La prueba automatizada usa una imagen mínima de demostración, **no** demuestra enfoque o legibilidad.

## Prueba manual y evidencias para Jira

1. Arrancar FastAPI desde `backend` con `uvicorn app.main:app --reload`; iniciar Vite con `npm run dev -- --host 0.0.0.0` desde `frontend`.
2. Usar `ipconfig` para identificar IP local del PC y entrar desde el teléfono por `http://IP_DEL_PC:5173` (misma red Wi-Fi, firewall habilitando 5173 solo en red confiable). El puerto 8000 puede permanecer cerrado a la LAN porque Vite lo proxifica localmente.
3. Abrir/crear un lote DEMO, registrar una pieza DEMO para recibir un `E-...` real. No reutilizar piezas de evaluaciones ajenas.
4. Tomar foto de una sola fruta con teléfono; revisar enfoque/encuadre. Para demostrar repetición, descartar o tocar «Repetir toma» antes de guardar.
5. Guardar una toma seleccionada, registrar `E-...`, `I-...`, nombre del archivo y pantalla de confirmación. Abrir el detalle de evaluación y comprobar `imageCount=1` y ruta `/api/images/I-...` accesible.
6. Comprobar error con un archivo no permitido y verificar que no se incremente `imageCount`.
7. Adjuntar capturas auténticas de las pantallas, log de ejecución de pruebas y PR a AGROP-26. **No indicar prueba física de teléfono completada hasta realizarla.**

## Limitaciones

- La captura «Repetir toma» se refiere a la selección previa a la carga inicial. No se reemplazan imágenes ya enviadas ni se programan vistas adicionales.
- La evaluación debe existir y seguir en estado `processing`. La fotografía está asociada a ese ID real, que actúa como identificador de evaluación en curso; no se inventan ID temporales locales.
- La política de pesaje sigue gestionada por los endpoints correspondientes. Las pruebas automatizadas no prueban el teléfono de Fernando ni el flujo de clasificación.
