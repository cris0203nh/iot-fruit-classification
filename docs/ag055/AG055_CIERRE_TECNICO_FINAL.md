# AG-055 / AGROP-67 — cierre técnico final

**Estado: desarrollo técnico completado; validación experimental pendiente.** Se entrega un prototipo E0/E1/E2 implementado, integrado y probado, con resultados experimentales limitados. Este cierre técnico no acredita precisión externa, variedad Kent, uso productivo ni aceptación funcional de requisitos no demostrados. No autoriza marcar AGROP-67 como Done sin aceptación formal del alcance reducido.

## Alcance implementado

- FastAPI: inferencia sobre fotografías persistidas, autenticación y permisos, versiones/hashes de modelo, instantáneas idempotentes y separación de propuestas frente a categorías originales y decisiones finales.
- React: modelos exploratorios anteriores, piloto V1 y V2 en paneles separados; propuesta no confirmada, puntuación no calibrada, versión y flujo de revisión/corrección con acceso al original y ROI.
- Historial de revisión con eventos nuevos y conservación del anterior; importación de etiquetas declaradas sin inventar metadatos ausentes. Las anotaciones automatizadas de E2E están identificadas y no cuentan como revisión humana auténtica.
- V2 mantiene SVC RBF, limita el descriptor a una máscara heurística de fruta, filtra matiz HSV por saturación y usa mediana/IQR con piso de escala ajustado solo en desarrollo. Fallos de segmentación devuelven `no_evaluable`, sin etiqueta ni puntuación forzadas. No confirma automáticamente grados.
- Inventarios, SHA-256, agrupaciones conocidas, control de duplicados, métricas y herramientas reproducibles. V1 y V2 se conservan; datos, modelos privados y evidencias completas quedan fuera de Git. La migración de propuestas está incluida como código, pero no se aplicó a SQLite original.

## Resultados realmente medidos

### Datos y revisión humana

Las **117 fotografías** del piloto tienen etiquetas humanas declaradas: mango 61 (20 E0, 20 E1, 21 E2), tomate 56 (20 E0, 17 E1, 19 E2). Se preservaron las etiquetas y sus originales. No constan revisor, fecha o rúbrica acreditados para esas 117; no se atribuyen a Junior Pérez ni se convierten en validación independiente.

Las **40 fotografías** posteriores fueron revisadas por Junior Pérez, según atribución y fecha declaradas por el usuario, **13/11/2026**. El CSV original conserva vacíos sus campos de revisor/fecha; la atribución se registra por separado, con precisión de día. Es evidencia humana declarada, sin acreditación de independencia física, cegamiento efectivo o rúbrica aprobada.

| Versión / evaluación | Producto | n medido | Accuracy | F1 macro | Alcance |
|---|---|---:|---:|---:|---|
| V1, exploratoria con etiquetas de Junior | Mango | 20 | 35,00 % | 0,1944 | Por fotografía; independencia no acreditada |
| V1, exploratoria con etiquetas de Junior | Tomate | 20 | 45,00 % | 0,2718 | Por fotografía; independencia no acreditada |
| V2, validación interna agrupada | Mango | 53 | **75,47 %** | 0,7559 | Selección interna, no prueba externa |
| V2, validación interna agrupada parcial | Tomate | 31 | **61,29 %** | 0,4074* | **Solo E1/E2; E0 no evaluado** |

*El cálculo registrado promedia tres clases asignando cero a E0, que no tiene soporte de validación. No estima rendimiento de tres clases; la media descriptiva de F1 exclusivamente E1/E2 es 0,6111. Todos los E0 tomate quedan en un único grupo: el fold que los retira deja al entrenamiento sin esa clase y se bloquea. No se fragmentó el grupo para aparentar cobertura completa.

V2 utiliza 100/117 imágenes segmentables: 53 mango y 47 tomate; rechaza 8 y 9 respectivamente. Cobertura técnica de desarrollo: **85,47 %**, distinta de precisión de segmentación o rendimiento externo. Los 17 rechazos permanecen contabilizados, sin cambiar sus etiquetas. El ajuste y la selección usaron exclusivamente desarrollo de las 117, con agrupaciones completas y escalado aprendido dentro de cada entrenamiento de fold. Las métricas internas son optimistas para generalización: no hay validación anidada ni identidad física demostrada.

La adaptación JSON coincidió con sklearn en las 100 imágenes aceptadas y la reproducción produjo los mismos parámetros y artefactos. Esto prueba reproducibilidad de software, no exactitud externa. **No se utilizaron las 40 fotos para entrenar, ajustar, seleccionar o medir V2; no se comparan estas cifras como mejora acreditada respecto a V1.**

El diagnóstico previo identificó dependencia de fondo, iluminación y encuadre, amplificación de bins HSV casi constantes y posibles discrepancias E1/E2. V2 corrige mecanismos técnicos; no demuestra que todos esos sesgos estén resueltos. F014 conserva una relación perceptual sin resolución documental con entrenamiento y no cuenta como independencia acreditada.

## Pruebas aprobadas y evidencias reutilizadas

Última aceptación completa existente: `AgroScan_AG055_V2_Aceptacion_03/acceptance.json`, con `passed=true` y archivos protegidos sin cambios:

| Verificación | Resultado existente |
|---|---|
| Backend, incluyendo regresiones AG-053/054 del entorno de aceptación | 238 aprobadas |
| Visión completa del entorno de aceptación | 571 casos: 569 aprobados, 2 omitidos |
| Frontend | 116 aprobadas |
| Compilación frontend y lint de calidad | Aprobados |
| Chromium real V1 y V2 | Aprobados: mango/tomate, foto rechazada, inferencia real, idempotencia, revisión, corrección e historial |
| Integridad y reproducibilidad | SHA-256 conservados; paridad JSON/sklearn; parámetros reproducidos |

Las pruebas E2E usan base y almacenamiento aislados. Las capturas, respuestas HTTP y logs completos están bajo `browser/` y `browser_v2/`; sus correcciones son automatizadas, no anotaciones agronómicas. Los recuentos completos corresponden al entorno local de aceptación de entonces, que también contiene trabajo independiente. Para el commit selectivo se verifica además la instantánea del índice y la vigencia por hashes de las fuentes AG-055; no se presenta el trabajo ajeno como parte de este PR. No se repite entrenamiento, auditoría ni batería completa para este cierre documental.

Comprobación mínima adicional del cierre sobre una copia del índice, sin cambios ajenos: backend AG-055 **23 aprobadas y 1 omitida** de 24 (evidencia I03 opcional no configurada en esa copia), visión AG-055 **41/41** y frontend AG-055 **13/13**. Se configuró JWT exclusivamente de prueba, sin copiar credenciales privadas. `git diff --cached --check` sin errores. Se reutilizan build, lint y E2E recientes al conservarse las fuentes probadas.

Evidencias privadas existentes bajo `%USERPROFILE%\Documents`:

- `AgroScan_AG055_E0E1E2_117_01`: manifiesto, importación declarada y modelos V1.
- `AgroScan_AG055_Evaluacion_Exploratoria_40_20261113_01`: CSV preservado, predicciones, matrices y métricas V1.
- `AgroScan_AG055_Diagnostico_40_03`: diagnóstico, relaciones y controles descriptivos.
- `AgroScan_AG055_V2_05`: modelos congelados, manifiesto, validación interna, hashes y `final_verification.json`.
- `AgroScan_AG055_V2_Aceptacion_03`: pruebas completas, E2E y conservación de SQLite/modelos.

La evidencia completa es local y privada; no queda disponible en GitHub por adjuntar este informe. Se incluyen en el repositorio código, pruebas y resúmenes técnicos; no datasets, CSV humanos, modelos privados, bases de datos ni fotografías.

## Límites y pendientes experimentales

| Requisito | Estado al cierre técnico |
|---|---|
| Prototipo integrado, versionado, revisión y correcciones | Implementado y probado |
| Rendimiento externo independiente E0/E1/E2 | **No acreditado** |
| Tomate E0 en validación interna agrupada | **No evaluado** |
| Identidad física, sesiones y separación independiente | **No acreditadas** |
| Variedad Kent | **Sin respaldo acreditado** |
| Rúbrica y coherencia experta de las 117 etiquetas | Pendiente; originales conservados, casos ambiguos señalados |
| Calibración probabilística y uso productivo | No acreditados; puntuaciones no calibradas |
| Reducción de trabajo manual | No medida; sin comparación real emparejada de tiempos/correcciones |
| Concurrencia del historial en despliegue multiworker | Limitación existente: bloqueo entre hilos de un proceso, sin garantía transaccional distribuida |

La revisión de inventarios AG-036/AG-055 no encontró candidatas acreditables para prueba externa. AG-036 conserva 97 fotos (38 mango, 59 tomate), sin identidad física/procedencia acreditadas ni respaldo Kent; su devolución de 30 etiquetas no resuelve esas carencias. En AG-055 quedan 7.305 registros únicos tras exclusiones y relaciones conocidas (772 mango, 6.533 tomate), sin etiquetas E0/E1/E2 elegibles ni independencia demostrada. Candidatas acreditadas por producto/clase: **cero en las seis combinaciones**. No se generó otro ZIP ni se inventó una distribución de clases para los remanentes.

Para acreditar rendimiento: resolver la rúbrica y discrepancias mediante decisiones humanas trazables; disponer de nuevas unidades de fruta/sesión acreditadas y clases representadas; congelar modelo, protocolo y criterio de aceptación antes de inferir; medir accuracy, F1 macro, recall por clase y cobertura incluyendo rechazos. Las 40 fotos ya consultadas siguen siendo diagnóstico histórico. Kent y eficiencia requieren evidencias propias. Respetar restricciones de licencia de las fuentes, incluido el alcance no comercial del material SEN utilizado.

## Conclusión y estado recomendado

**Se completa el desarrollo técnico del prototipo AG-055, con integración y pruebas verificables y validación experimental limitada.** Se conserva la distinción entre implementación funcional, medición interna/exploratoria y aceptación externa. AGROP-67 debe reflejar **«desarrollo técnico completado; validación experimental pendiente»**. La aceptación formal de un alcance reducido corresponde al responsable del producto; hasta entonces no marcar Done ni declarar satisfechos los requisitos experimentales anteriores. El PR requiere revisión y no se fusiona automáticamente.

Referencias: [V2](AG055_V2.md), [evaluación exploratoria de 40](AG055_EVALUACION_EXPLORATORIA_40.md), [diagnóstico](AG055_DIAGNOSTICO_ERRORES_40.md), [piloto de 117](AG055_VALIDACION_E0E1E2.md). Este informe fija la conclusión final; los documentos de incrementos anteriores conservan su contexto histórico.
