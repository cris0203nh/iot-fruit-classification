# AG-055 I05 — Auditoría final y cierre técnico

**Resultado:** software experimental aceptado técnicamente para uso local supervisado,
con las restricciones indicadas abajo. **No se recomienda cerrar AGROP-67 globalmente
como clasificación E0/E1/E2 validada ni autorizar producción.**

Rama `feature/AGROP-67-calidad-externa`; base Git `a88ebcccdcd7aa708bbb6265057b282af319b8ab`.
La entrega incluye cambios locales sin commit; sus hashes se registran en la evidencia.
Fecha local: 12 de noviembre de 2026, America/Lima; registros de aplicación en UTC.
No se reentrenaron modelos AG-055, cambiaron umbrales, ejecutaron migraciones ni abrieron PR.

## 1. Auditoría de integridad y versiones

La auditoría de solo lectura reprodujo las métricas de **los tres modelos guardados**
en validación y prueba, con los descriptores, ROI y etiquetas originales congelados.
Verificó 9.262 imágenes, 9.317 archivos de paquetes, ambos ZIP originales y las 1.605
relaciones conocidas; no hay duplicados exactos retenidos ni cruces conocidos de grupos.
Esto **no demuestra independencia física de fruta/sesión**, ni exhaustividad de deduplicación.

- Modelo: `ag055-original-labels-v1`; descriptor: `rgb-hsv-hist-grid-v1`.
- Routing: `ag055-review-routing-v1`.
- Datos: `8b855bc074d3549f3e350e3a3a822d078d859f89734dd2dbc3c40ffebb15c020`.
- Política I04: SHA-256 `3077767a0f552715b1e833dfdeed874b6a6c2cd6cb00f6a113067fb84dbcd73a`.
- Los modelos, sus parámetros, manifests, fotografías, SQLite original y siete archivos
  con cambios independientes conservan su contenido. La comparación final cubre
  **9.369 archivos privados** respecto a la línea base tomada antes de esta auditoría.

Las métricas de candidatos no seleccionados se conservan como evidencia histórica de I03;
sus pesos no fueron exportados y no se reentrenaron para volver a medirlos.
Las licencias/procedencia conservadas en los paquetes no acreditan Kent ni las etiquetas
E0/E1/E2. SEN mantiene el alcance de investigación no comercial declarado en su licencia.

## 2. Defectos propios corregidos y pruebas de recuperación

1. Un fallo durante la escritura podía publicar un JSON parcial y bloquear el historial.
   Ahora se escribe y sincroniza un temporal y se publica el archivo completo mediante
   enlace duro exclusivo, sin reemplazar destinos. Una escritura interrumpida no añade un evento.
2. Historial ilegible, lectura de foto denegada y fallo de persistencia SQL devolvían errores
   no controlados. Ahora se responde 503, se conserva la evidencia y se revierte la transacción
   SQL fallida. No se borran ni ignoran automáticamente archivos de historial dañados.
3. Una fotografía con bytes alterados pero igual tamaño podía producir otra inferencia.
   Se compara ahora con los hashes de los snapshots anteriores del mismo ID y se rechaza
   con 409 antes de inferir. Antes del primer análisis no existe ese anclaje en los snapshots;
   no se presenta el control de tamaño del registro como prueba criptográfica de la captura inicial.
4. Una prueba antigua de render escribía su HTML dentro de I03. La comprobación de
   preservación detectó esa escritura; se restauró el HTML previo **byte por byte**, comprobando
   su SHA-256, y se corrigió el test. Desde ahora la referencia es solo lectura y cualquier HTML
   nuevo exige una salida explícita y creación exclusiva. La aceptación final protege también ese hash.

Los cinco tests nuevos de backend fallaron antes de las correcciones y pasan después.
Se conservan `defects_before_fix.log`, las pruebas finales y `render_restoration.json`.
El estado final de los archivos privados coincide con la línea base, no solo con el último ensayo.

## 3. Rendimiento experimental reproducido

Métricas de prueba interna agrupada; **no son validación agronómica externa**:

| Tarea | N | Accuracy | Precision macro | Recall macro | F1 macro |
|---|---:|---:|---:|---:|---:|
| TQ Fresh/Rotten | 369 | 0,8455 | 0,8633 | 0,8416 | 0,8424 |
| SEN, cinco clases originales | 169 | 0,7633 | 0,7612 | 0,7547 | 0,7563 |
| SEN Healthy/enfermedades listadas, scores agrupados | 169 | 0,9586 | 0,9470 | 0,9395 | 0,9432 |
| FGrade, diez códigos originales | 1260 | 0,3317 | 0,2192 | 0,1947 | 0,1903 |

FGrade permanece solo diagnóstico y no apto para decisiones operativas. El agrupamiento
SEN no acredita detección de todo defecto, diagnóstico fitopatológico ni variedad Kent.
La matriz TQ sigue siendo `[[182,9],[48,130]]`, filas/columnas Fresh, Rotten.

## 4. Incertidumbre con política congelada

No se ajustó ningún umbral con prueba. TQ prioriza score Rotten ≥0,0225843969,
margen ≤0,9629270508 o predicción Rotten. SEN prioriza margen ≤0,7035698619 o
categoría de enfermedad. Todos los resultados, incluso prioridad normal, requieren revisión humana.

| Conjunto | Priorizadas / total | Carga prioritaria | Errores cubiertos | Rotten→Fresh cubiertos |
|---|---:|---:|---:|---:|
| TQ validación | 243/396 | 61,36% | 45/48 = 93,75% | 36/39 = 92,31% |
| TQ prueba | 256/369 | 69,38% | 55/57 = 96,49% | 46/48 = 95,83% |
| SEN validación | 138/166 | 83,13% | 50/50 = 100% | No aplica |
| SEN prueba | 140/169 | 82,84% | 38/40 = 95% | No aplica |

En TQ se priorizan 83/86 Rotten de validación (96,51%) y 176/178 de prueba (98,88%).
El objetivo de retener ≥95% de Rotten de validación **no equivale** a cubrir ≥95% de
los falsos negativos ni a una garantía sobre futuras fotografías. Los percentiles y la
cobertura de errores son mediciones distintas. **No hay estudio de tiempos ni reducción
demostrada del trabajo manual**: la tabla cuantifica prioridad, no fotos aprobadas automáticamente.

### Dos Rotten→Fresh de prueba que no reciben prioridad

| ID | Score Fresh | Score Rotten | Margen | ROI xywh |
|---|---:|---:|---:|---|
| TQ_001342 | 0,990431 | 0,009569 | 0,980862 | `[155,240,382,464]` |
| TQ_001344 | 0,987024 | 0,012976 | 0,974047 | `[460,307,750,383]` |

Ambos márgenes superan el límite y ambos scores Rotten quedan por debajo del umbral.
Son errores con scores extremos; **Confianza no calibrada** sigue siendo obligatorio.
No se modificaron sus etiquetas originales ni se generaron grados E0/E1/E2.

Observación visual **de IA, no revisión humana ni diagnóstico**: TQ_001342 muestra una
zona oscura localizada en el borde inferior derecho; TQ_001344 presenta superficie arrugada
y una ROI que incluye una zona amplia de fondo a la derecha. El predominio de color rojo,
los descriptores agregados y el fondo son hipótesis de fallo que requieren experimentos
independientes; esta inspección no establece causalidad ni corrige el ground truth.
Identificadores, hashes completos, rutas privadas y scores están en `frozen_audit_complete.json`.

## 5. Aceptación funcional, seguridad y persistencia

Chromium real ejecutó React/FastAPI con una foto persistida del dataset y modelos reales:
autenticación, inferencia, acceso autenticado al original/ROI, revisión, corrección mediante
nuevo evento, reautenticación y recuperación de historial, reintento idempotente y móvil 390×844.
El ensayo final tiene dos snapshots de inferencia, dos eventos de prueba y **cero grados
confirmados**. No es un HTML estático presentado como interacción E2E.

Se comprobaron HTTP reales 401 sin sesión, 403 para POST de la cuenta revisor de consulta,
y 409 sin fotografía. Las pruebas backend verifican además campos de suplantación,
ROI/evidencia alterada, modelo inválido, edición obsoleta, integridad y recuperación de almacenamiento.
Los casos de UI de ausencia de modelo, desconexión, falta de foto y almacenamiento 503
usan fallos inyectados por Playwright, distinguidos expresamente de la inferencia exitosa real.

La revisión reutiliza la cola existente y toma el revisor de la sesión, exige declaración
explícita y conserva `supersedesEventId`, foto SHA, inferencia, modelo, fecha y justificación.
Las categorías originales y las anotaciones E0/E1/E2 siguen separadas; no se escriben
`visual_category` ni decisiones oficiales. No se autoacreditan etiquetas ni doble revisión.

**Límites:** publicación de archivos validada en NTFS local con enlaces duros; no se acredita
persistencia transaccional multiworker/distribuida. El bloqueo de revisión es entre hilos de
un proceso. Los mecanismos de aplicación no convierten archivos/SQLite en almacenamiento
WORM ni impiden modificaciones administrativas externas. Mantener un solo escritor y respaldos.

## 6. Pruebas completas y evidencias

| Verificación final | Resultado |
|---|---|
| Backend completo, incluidas AG-053/054 y cinco regresiones I05 | 232 aprobadas, 0 fallos |
| Visión completa | 553 casos: 551 aprobados, 2 omitidos, 0 fallos |
| Frontend completo | 111 aprobadas, 0 fallos |
| TypeScript/Vite y ESLint de calidad/cliente API | Correctos |
| E2E Chromium 156.0.8078.4 / Playwright 1.65.0 | Aprobado, sin excepciones JavaScript |

Las dos omisiones son pruebas de enlaces simbólicos de AG-034/AGROP-42 no disponibles
con los permisos actuales de Windows. No se cambiaron permisos del sistema.
El primer intento global detectó dependencias de tests ausentes y codificación Windows;
se resolvió con `PYTHONUTF8=1` y dependencias de visión externas, sin editar módulos ajenos,
NumPy/Pillow existentes ni dependencias del repositorio. El lint global conserva los problemas
ajenos documentados en I04; no se declara un lint global limpio.

Carpeta privada final: `%USERPROFILE%\Documents\AgroScan_AG055_I05_01`:

- `acceptance_verified/acceptance.json`: códigos de salida y hashes antes/después.
- `acceptance_verified/backend_tests.log`, `vision_tests.log`, `frontend_tests.log`,
  `frontend_build.log`, `quality_lint.log`, `browser_e2e.log`: logs completos.
- `acceptance_verified/api_server.log`, `vite_server.log`: servidores aislados.
- `acceptance_verified/browser/`: capturas reales, resultados, consola, red y respuestas sanitizadas.
  No se guardan contraseñas ni cabeceras Authorization en estos logs de navegador.
- `frozen_audit_complete.json`: métricas, matrices, versiones, integridad y casos no priorizados.
- `baseline.json`, `preservation_and_annotation_audit.json`, `final_validation.json`,
  `SHA256SUMS.json`: preservación y trazabilidad de la entrega.
- Los intentos anteriores y sus incidencias quedan separados; el aceptado es **acceptance_verified**.

## 7. Evidencia humana y matriz de aceptación para Jira

Los seis eventos I04 y los dos de la aceptación final I05 son **anotaciones automatizadas
de ensayo**, identificadas como `automated_test_not_human_ground_truth` y excluidas del
entrenamiento humano. No se aportó ni creó nueva revisión humana auténtica acreditada de
E0/E1/E2. Las referencias anteriores AG-036 y decisiones humanas históricas no se convierten
automáticamente en ground truth elegible; esta auditoría no certifica su autenticidad/competencia.

| Criterio | Estado | Evidencia o pendiente |
|---|---|---|
| Foto persistida → inferencia real → React | Cumplido | E2E y capturas reales |
| Estado experimental, scores y versiones visibles | Cumplido | React/HTTP; confianza no calibrada |
| Routing derivado solo de validación | Cumplido | Política congelada y SHA verificados |
| Revisión/corrección/historial sin modificar predicción | Cumplido, un proceso | Dos eventos enlazados; snapshots originales intactos |
| Autenticación y permisos | Cumplido | HTTP reales y tests de autorización |
| Idempotencia y recuperación de escritura fallida | Cumplido | E2E y regresiones I05 |
| SHA y ausencia de fugas conocidas | Cumplido con límites | Integridad digital; no acredita independencia física |
| Regresiones AG-053/054, tests y build | Cumplido | Backend/visión/frontend; dos omisiones ambientales documentadas |
| FGrade excluido de decisiones operativas | Cumplido | Solo diagnóstico, F1 macro 0,1903 |
| Revisión humana competente y rúbricas aprobadas | Pendiente externo | Evidencia real, no eventos E2E |
| Clasificador E0/E1/E2 acreditado | No cumplido | Clases/ROI/soportes y evaluación externa independientes |
| Mango Kent acreditado e independencia por fruta/sesión | No cumplido | Identidad/variedad y validación específicas |
| Confianza calibrada y validación de estación | No cumplido | Datos y protocolo aprobados por producto/cámara |
| Reducción medida de trabajo manual | No demostrado | Falta estudio de tiempos/capacidad y aceptación de riesgo |
| Uso productivo / multiworker | No autorizado | Aprobación externa y transacciones entre procesos pendientes |

**Estado recomendado para AGROP-67:** mantener abierto/en revisión, pendiente de validación
externa. Registrar el **cierre técnico del software experimental I01–I05** y vincular la evidencia;
no marcar Done global si el alcance exige clasificación E0/E1/E2 validada. No se actualizó Jira.

## 8. Archivos de I05 y comandos mínimos Windows

Correcciones: `vision/ag055/review.py`, `backend/app/routers/quality_prediction.py`,
`frontend/tests/ag055-quality.test.mjs`.
Pruebas/herramientas: `backend/tests/test_ag055_i05_audit.py`,
`backend/tests/ag055_i04_app.py`, `frontend/tests/ag055-i04-e2e.mjs`,
`vision/ag055/audit_i05.py`, `vision/ag055/acceptance_i05.py` y este informe.

Desde la raíz del repositorio, escoger salidas **nuevas**:

```powershell
$base = "$env:USERPROFILE\Documents"
py -3.13 -m vision.ag055.audit_i05 `
  --run "$base\AgroScan_AG055_I03_run02" --i04 "$base\AgroScan_AG055_I04_01" `
  --output "$base\AG055_auditoria_repeticion01.json"
py -3.13 -m vision.ag055.acceptance_i05 `
  --run "$base\AgroScan_AG055_I03_run02" --i04 "$base\AgroScan_AG055_I04_01" `
  --output "$base\AG055_aceptacion_repeticion01" `
  --playwright-root "$base\AgroScan_AG055_I04_tools" `
  --chromium "$env:LOCALAPPDATA\ms-playwright\chromium-1248\chrome-win64\chrome.exe" `
  --vision-deps "$base\AgroScan_AG055_I05_tools\python"
```

El ejecutor usa Python original 3.13, configura UTF-8 y las rutas de dependencias solo
para sus procesos, rechaza puertos 18004/5174 ocupados y detiene sus servidores al terminar.
No ejecutar la aplicación fixture para revisiones reales. Las instrucciones de uso supervisado
de AgroScan y sus variables de entorno permanecen en el informe I04.

Dependencias opcionales instaladas fuera del repositorio para la suite completa: scikit-learn
1.9.1, SciPy 1.18.1, joblib 1.6.0, threadpoolctl 3.8.0, cloudpickle 3.1.2 y narwhals 2.28.0.
Los estimadores temporales de los tests legados usan fixtures sintéticos; no reentrenan los
modelos AG-055 ni aportan métricas agronómicas a esta entrega.
