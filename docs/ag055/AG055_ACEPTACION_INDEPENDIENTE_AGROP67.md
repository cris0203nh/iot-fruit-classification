# AG-055 — Revisión ciega y aceptación independiente pendiente

Fecha: 13 de noviembre de 2026. Rama `feature/AGROP-67-calidad-externa`.
**Entrega realizada: paquete ciego de las 40 candidatas. AGROP-67 permanece abierto.**
La evaluación final no puede ejecutarse todavía: no se han recibido etiquetas ciegas
ni documentación de independencia física. No se ajustaron modelos ni umbrales.

## Entrega al revisor y separación de custodia

Carpeta privada final: `%USERPROFILE%\Documents\AgroScan_AG055_Revision_Ciega_40_02`.

- **Enviar al revisor únicamente `AG055_Revision_Ciega_40.zip`.** Contiene 40 JPG
  originales numerados F001–F040, instrucciones, licencias, CSV vacío, formulario HTML
  offline y manifiesto SHA-256. No contiene predicciones, scores, nombres originales,
  clases de fuente, etiquetas sugeridas, mapas de entrenamiento ni alertas de similitud.
- **No enviar `AG055_Custodia_NO_ENVIAR_AL_REVISOR.zip` al revisor ciego.** Conserva
  ID/ruta originales, fuente/autor/licencia, mapa a F001–F040, hashes, auditoría de
  relaciones y formulario de identidad/independencia para el custodio.

Los 40 originales se mantienen byte por byte: no se recodificaron ni alteraron.
Los metadatos encontrados son JFIF/densidad/DPI, sin nombres originales o etiquetas
EXIF aportados. No se garantiza que una persona no pueda reconocer escenas previamente
conocidas; se exige declarar exposición previa. No debe consultar fuentes con clases,
predicciones ni mapa de custodia durante la revisión.

El orden está mezclado y numerado; el mapa original queda preservado por separado para
no revelar pistas como carpetas de enfermedad. El formulario no preselecciona un grado,
revisor, fecha ni rúbrica. La fecha real debe introducirla quien revisa; no se toma de
archivos ni importación. La versión HTML funciona sin servidor ni solicitudes a Internet,
permite navegar y descargar el CSV; no conserva cambios después de cerrar/recargar.

### Instrucciones mínimas

1. Extraer el ZIP completo y leer `INSTRUCCIONES.md`.
2. Abrir `formulario.html` o completar `formulario.csv` sin alterar IDs/productos/SHA.
3. Anotar E0/E1/E2/no_evaluable, justificación, ubicación de evidencia, Rxx para E1/E2,
   rúbrica real, revisor real, fecha ISO con zona horaria y soporte auténtico relativo.
4. Dejar duración vacía si no se midió con un cronómetro real. No estimarla desde archivos.
5. Descargar el CSV y devolverlo con sus soportes en una carpeta `soportes/`. Conservar
   versiones anteriores si se corrige una revisión; no reemplazar los originales.

La identidad física no debe adivinarla el revisor viendo la foto: el custodio debe
obtener registros reales de fruta/sesión y resolver relaciones con entrenamiento.
Un ID nuevo por foto, nombres distintos o SHA distintos no demuestran independencia.

## Resultado de auditoría de las 40 frente a las 117

| Comprobación | Resultado |
|---|---|
| Candidatas verificadas por SHA y decodificación | 40: 20 mango genérico, 20 tomate |
| Fotos de entrenamiento verificadas | 117 |
| Duplicados de bytes/píxeles entre candidatas | 0 / 0 |
| Coincidencias exactas con entrenamiento | 0 |
| Pares perceptuales candidata–candidata detectados | 0 con el método declarado |
| Pares perceptuales candidata–entrenamiento | 1, pendiente de resolución |
| Frutas físicamente independientes acreditadas | 0 mango, 0 tomate |
| Clases E0/E1/E2 de las candidatas | Pendientes, no inferidas |
| Accuracy/precision/recall/F1/matriz independientes | No evaluados |

Método: orientación EXIF, gris 32×32 bicúbico, DCT 8×8 sin DC, umbral de mediana,
63 bits y distancia mínima sobre ocho rotaciones/reflexiones D4, candidato Hamming ≤8.
Es heurístico y no exhaustivo: no detectar similitud **no prueba** independencia.

**F014** (ID original `TQ_001517`) tiene distancia 8 con una fotografía de entrenamiento
`pilot117_00f307fc985211e52db4`. No comparten bytes/píxeles exactos. Se conserva dentro
del paquete para la revisión ciega, pero no será elegible para evaluación independiente
hasta documentar la resolución de esta relación. La alerta queda solo con el custodio.
Las restantes 39 tampoco están acreditadas por el mero hecho de no tener alertas.

Procedencia: SEN/MangoFruitDDS, CC BY-NC 3.0, y TQ/Project-AgML, CC BY 4.0, con
atribuciones conservadas. No hay IDs de fruta/sesión acreditados en estos registros.
Kent no se acredita. Las candidatas pueden haber participado en los exploratorios I03;
no constituyen por sí mismas una evaluación independiente del sistema completo.

## Cuántas muestras faltan

El número físico real es **desconocido**, no cero: cero es el número que puede acreditarse
actualmente con los soportes disponibles. Sin etiquetas ciegas no se conoce la distribución
por categoría y no se puede determinar el número definitivo de **nuevas capturas** por clase.

Frente al piso técnico heredado de AG-034/I02 de cinco componentes por producto/grado:

| Producto | E0 acreditados / faltantes | E1 acreditados / faltantes | E2 acreditados / faltantes |
|---|---:|---:|---:|
| Mango genérico | 0 / 5 | 0 / 5 | 0 / 5 |
| Tomate | 0 / 5 | 0 / 5 | 0 / 5 |

Faltan **30 unidades acreditadas** para ese piso de planificación. Esto no significa
automáticamente 30 fotos nuevas: algunas candidatas podrían cubrirlo si sus etiquetas
y documentación resultan elegibles. Si ninguna puede acreditarse, serán necesarias al
menos cinco frutas nuevas independientes por clase y producto para alcanzar ese piso.
**Cinco no es un tamaño aprobado ni suficiente para la aceptación científica final.**
El objetivo definitivo requiere protocolo/tamaño muestral aprobado según precisión deseada,
riesgo E2→E0 y cobertura de producto/cámara/sesión. No se inventa ese criterio de cierre.

## Evaluación posterior y condición de elegibilidad

Se implementó `vision.ag055.blind_review evaluate`. Después de recibir revisiones y
documentación reales, verifica IDs/hash, modelos congelados, grado, revisor/fecha/rúbrica,
evidencia, cegamiento declarado, fruta/sesión/soportes y resolución de similitudes.
Excluye no evaluables, coincidencias con entrenamiento y vistas adicionales de la misma
fruta documentada. Los campos y archivos son declaraciones documentales: el software
no autentica su legitimidad ni la competencia del revisor.

Para productos con cobertura suficiente calcula n, sesiones, matriz de confusión,
accuracy y precision/recall/F1 por clase y macro. No calibra ni ajusta umbrales.
No promueve métricas como acreditación automática ni cierra Jira.
Al comprobar los formularios vacíos actuales, ambos productos quedan bloqueados con
**n=0 y metrics=null**; no se ejecutó inferencia para fabricar métricas.

```powershell
$base = "$env:USERPROFILE\Documents"
$env:PYTHONPATH = "$PWD;$PWD\backend\.venv\Lib\site-packages"
# Ejecutar SOLO tras recibir etiquetas y soportes reales:
py -3.13 -m vision.ag055.blind_review evaluate `
  --package-root "$base\AgroScan_AG055_Revision_Ciega_40_02" `
  --pilot-run "$base\AgroScan_AG055_E0E1E2_117_01" `
  --reviews '<devolucion>\formulario_completado.csv' `
  --identity '<custodia>\identidad_independencia.csv' `
  --supports '<raiz_con_soportes_reales>' --output '<informe_nuevo.json>'
```

No hay mediciones manual/asistido emparejadas, por lo que no se calculó ahorro de tiempo
ni reducción de correcciones. Registrar duración manual real no basta para una comparación
causal: hace falta una fase asistida posterior, diseño aprobado y control del aprendizaje.

## Matriz de aceptación para Jira AGROP-67

| Requisito | Estado |
|---|---|
| Software de inferencia/revisión I01–I05 y piloto 117 | Aprobado técnicamente, con límites previos |
| Paquete de 40 imágenes ciego y trazabilidad separada | Entregado y verificado |
| Integridad y análisis de relaciones | Ejecutados; F014 pendiente de resolución |
| Revisión humana ciega de las 40 | Pendiente de devolución auténtica |
| Independencia física por fruta/sesión | Pendiente; ninguna acreditada actualmente |
| Métricas finales por producto/clase | Pendientes; no evaluadas |
| Comparación de tiempos/correcciones | Pendiente de mediciones reales |
| Kent, calibración/estación, aceptación de riesgos | No acreditados/pendientes |
| Cierre experimental final AGROP-67 | **No autorizado; mantener abierto/en revisión** |

La inspección del ZIP verificó los 40 originales y todos sus hashes, campos humanos vacíos
y ausencia de archivos de predicciones/mapas originales en el paquete ciego. Se probó el
HTML en Chromium real: navegación, imágenes locales, campos vacíos y exportación CSV,
sin errores JavaScript ni red externa. El motor bloquea evaluación al no recibir etiquetas.
Los modelos, ZIP/datasets originales y SQLite permanecen sin cambios; las pruebas y
archivos de revisión viven fuera de Git. No se actualizó Jira, ni se creó rama o PR.
