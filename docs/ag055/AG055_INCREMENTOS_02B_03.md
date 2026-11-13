# AG-055 — Incrementos 02B y 03: experimento real

Ejecución local del 12 de noviembre de 2026, rama `feature/AGROP-67-calidad-externa`.
Software implementado y modelos exploratorios entrenados. **E0/E1/E2 no acreditado.**
No se desplegó en producción ni se cambiaron categorías humanas o decisiones históricas.

## Datos y controles

- ZIP Real: 9.245 imágenes; Selectivo: 17. Se verificaron 9.280 y 37 archivos,
  respectivamente, contra sus manifiestos SHA-256, además de decodificar las 9.262 imágenes.
- Fotografías, licencias originales, modelos y registros privados permanecen fuera de Git.
  Se conservó la primera preparación en `Documents/AgroScan_AG055_I03_run01`;
  **la ejecución final es `Documents/AgroScan_AG055_I03_run02`**, que referencia las mismas fotos.
- Hay 14 copias exactas excedentes. Dos pares FGrade tienen etiquetas contradictorias
  (2/3 y 8/9): se excluyen **los cuatro miembros**, sin elegir una etiqueta arbitrariamente.
  Exclusión final: 12 copias redundantes + 4 archivos contradictorios + 17 candidatas
  sin etiqueta original utilizable para esta tarea = 33. Se usan 9.229 imágenes.
- Se unieron transitivamente las 1.605 relaciones suministradas, grupos visuales,
  hashes de bytes/píxeles, fechas sugeridas por nombres TQ y familias de nombres FG
  entre carpetas y clases. Las relaciones se preservan antes de cualquier partición.
- Auditoría final: cero duplicados exactos retenidos y cero cruces conocidos de
  componentes entre entrenamiento, validación y prueba. **No demuestra independencia física**:
  no hay diccionario acreditado de fruta/sesión; pueden persistir multivistas desconocidas.
- ROI mediante caja cromática automática, con imagen completa como fallback explícito.
  No se presenta como segmentación ni revisión humana. Todas las ROI quedan sin verificar.
  Imágenes con varias frutas, fondos, rótulos y atajos de adquisición siguen siendo limitaciones.

Licencias y categorías contrastadas con documentación conservada y fuentes primarias:
[TQ](https://data.mendeley.com/datasets/s42kpg8h37/1), CC BY 4.0, autores Khatun,
Razzak, Islam y Uddin; espejo Project-AgML.
[SEN](https://data.mendeley.com/datasets/jvszp9cbpw/3), CC BY-NC 3.0, Faye, Diop,
Mbaye, Diedhiou y Dione: **experimento de investigación no comercial**, sin acreditar Kent.
[FGrade](https://github.com/skarifahmed/FGrade), MIT, Das, Kar y Sekh.
Los avisos originales permanecen con los datos y la atribución en cada artefacto.
El cotejo con el contenedor primario SEN/TQ no queda acreditado por verificar el ZIP recibido.
Las 17 candidatas conservan sus licencias y procedencia; no se convierten en ejemplos
supervisados por sus nombres o categorías candidatas E0/E1/E2.

## Resultados reales

Semilla 55. Descriptor RGB/HSV, histogramas y cuadrantes de ROI; normalización ajustada
solo con entrenamiento. Baseline de centroides frente a softmax L2 con 500 iteraciones,
tasa 0,05 y L2 en {0,001; 0,01}. Selección exclusiva por F1 macro de validación.
No hay reentrenamiento con prueba, aumentos ni datos sintéticos de rendimiento.

| Tarea | Train / validación / prueba | Grupos por partición | Ganador |
|---|---:|---:|---|
| TQ Fresh/Rotten | 1221 / 396 / 369 | 10 / 9 / 10 | Softmax L2 0,001 |
| SEN, cinco clases originales | 518 / 166 / 169 | 507 / 162 / 167 | Softmax L2 0,01 |
| FG, códigos originales 0–9 | 3851 / 1279 / 1260 | 29 / 17 / 12 | Centroides |

Métricas del ganador en **prueba interna agrupada**, no validación externa:

| Tarea | Accuracy | Precision macro | Recall macro | F1 macro |
|---|---:|---:|---:|---:|
| TQ Fresh/Rotten | 0,8455 | 0,8633 | 0,8416 | 0,8424 |
| SEN, cinco clases | 0,7633 | 0,7612 | 0,7547 | 0,7563 |
| SEN Healthy / enfermedades listadas | 0,9586 | 0,9470 | 0,9395 | 0,9432 |
| FG, diez códigos originales | 0,3317 | 0,2192 | 0,1947 | 0,1903 |

SEN binario suma los scores de las cuatro enfermedades originales; no es diagnóstico
clínico, detector de todo defecto ni conversión a E0/E1/E2. Su modelo se seleccionó
por la validación de cinco clases, sin optimizar sobre prueba.
FG respeta los códigos originales de carpetas, sin asumir correspondencia formal
con días, E0/E1/E2 o grados 1–10. Su rendimiento es débil; no permite uso decisorio.

| Tarea | F1 validación: centroides / mejor softmax | F1 prueba: centroides / softmax seleccionado por validación |
|---|---:|---:|
| TQ | 0,5898 / 0,7941 | 0,6650 / 0,8424 |
| SEN | 0,6550 / 0,7053 | 0,6445 / 0,7563 |
| FG | 0,2140 / 0,1840 | 0,1903 / 0,1613 |

Matriz TQ (filas reales, columnas predichas, orden Fresh/Rotten): `[[182,9],[48,130]]`.
Recall Rotten: 0,7303; 48 de 178 Rotten se predijeron Fresh.
Las matrices completas, métricas por clase y por candidato, versiones, semillas y parámetros
están en `run02/report.json` y en cada modelo. `manifest.json` registra exclusión, grupo,
partición, hash y ROI por imagen. `execution_evidence.json` registra la auditoría y hashes.

## Integración y revisión

`vision/ag055/experimental.py` prepara, audita, entrena y predice con NumPy/Pillow.
La API reutiliza autenticación, imágenes persistidas y la tabla append-only de I01:

- `GET /api/evaluations/{id}/vision/quality/exploratory/status`
- `POST /api/evaluations/{id}/vision/quality/exploratory/analyze` (operador/administrador)
- La consulta existente `/vision/quality/proposals` también conserva el historial exploratorio.

Los snapshots nuevos tienen `proposedGrade=null`, fuente/modelo SHA-256, scores no
calibrados y resultado por imagen. El panel React distingue estos resultados de las
propuestas E0/E1/E2 y muestra etiquetas, confianza, versión y limitaciones.
No se añaden tablas: se verificó en lectura la migración existente `b055a1b2c3d4`.
La SQLite del usuario no fue modificada. Se creó un respaldo externo con
`sqlite3.backup`, integridad OK y recuentos iguales en las 18 tablas; el hash del original
permaneció intacto. Ver `run02/sqlite_backup_verification.json` para el número efectivo de tablas.

La cola local `vision/ag055/review.py` permite filtrar, seleccionar foto, observar/ajustar
ROI y registrar grado humano, revisor, fecha UTC, rúbrica y evidencia visual. E1/E2
exigen criterio Rxx. Cada revisión y corrección crea un evento nuevo; no modifica originales.
No se declara revisión humana hasta que una persona la guarde expresamente.
`train-reviewed` permite comparar posteriormente tres clases revisadas, conservando grupos
y exigiendo cinco componentes por grado y una rúbrica consistente por producto.
Los artefactos revisados siguen sin acreditación y no se instalan en la API E0/E1/E2.
Las exclusiones por duplicación/conflicto/procedencia no se levantan al anotar una foto.
No se exige ArUco para este entrenamiento.

## Windows: ejecución mínima desde la raíz

```powershell
$run = "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run02"
# Revisión humana local (no crea anotaciones automáticamente):
py -3.13 -m vision.ag055.review serve --run $run
# Abrir http://127.0.0.1:8055; detener con Ctrl+C.
```

Para habilitar la inferencia local en AgroScan, iniciar FastAPI con:

```powershell
$env:AGROSCAN_EXPLORATORY_MODELS_PATH = "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run02\models"
Push-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
# En otra terminal: cd frontend; npm run dev
```

Iniciar sesión como operador, abrir una evaluación con fotos persistidas y pulsar
«Explorar fotografías persistidas» en captura o trazabilidad. El respaldo verificado
corresponde al estado de esta ejecución; renovarlo antes de migraciones posteriores.
No copiar los JSON exploratorios como modelos E0/E1/E2.

Repetir el experimento en una salida **nueva**, sin duplicar fotos:

```powershell
py -3.13 -m vision.ag055.experimental `
  --prepared-run "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run01" `
  --output "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run03" --seed 55
# Para una preparación desde cero: --real-zip <ZIP> --selective-zip <ZIP> --output <carpeta nueva>
py -3.13 -m vision.ag055.review train-reviewed --run $run `
  --output "$env:USERPROFILE\Documents\AgroScan_AG055_E0E1E2_revisado_01"
```

El intérprete original Python 3.13 tiene NumPy/Pillow y puede escribir fuera del repositorio.
No se reinstaló Python, no se cambiaron permisos ni se instalaron dependencias.

## Pruebas y evidencia

- Vision AG-055: 20/20; backend AG-055: 9/9, incluida inferencia con fotos reales.
- Frontend: 109/109; build TypeScript/Vite correcto. ESLint de los módulos AG-055 y
  cliente API correcto; lint global conserva 8 errores y 4 advertencias en módulos ajenos.
- Cola HTTP real: 9.262 entradas, foto orientada decodificable y escritura sin token rechazada.
- `run02/fastapi_real_evidence.json`: respuestas autenticadas sobre fotos reales de prueba,
  persistidas en una SQLite temporal de ensayo, sin tocar la base del usuario.
- `run02/react_real_evidence.html`: render del componente React con **esas mismas respuestas**.
  No equivale a una prueba de clics de navegador contra una sesión del usuario.
- `run02/final_validation.json`: resultados finales, hashes del código y verificación de
  tamaño, dimensiones, formato y SHA-256 contra los 9.262 registros de metadatos de imagen.

```powershell
py -3.13 -m unittest discover -s vision/tests -p 'test_ag055_*.py' -v
$env:PYTHONPATH = "$PWD;$PWD\backend;$PWD\backend\.venv\Lib\site-packages"
$env:AG055_REAL_RUN = "$env:USERPROFILE\Documents\AgroScan_AG055_I03_run02"
py -3.13 -m unittest discover -s backend/tests -p 'test_ag055_*.py' -v
Push-Location frontend
npm test
npm run build
npx eslint src/features/quality src/services/agroscanApi.ts
Pop-Location
```

## Lo que impide cerrar AGROP-67

1. Etiquetas E0/E1/E2 humanas competentes y rúbricas aprobadas, con ROI/evidencia por vista;
   actualmente no hay nuevas anotaciones reales creadas por esta ejecución.
2. Identidad de fruta/sesión y conjunto independiente externo: los grupos técnicos no la prueban.
3. Variedad Kent acreditada y cobertura suficiente por cada grado para el alcance mango Kent.
4. Validación en estación física, cámaras/iluminación y cambio de dominio de ROI;
   ArUco pertenece a esa validación de estación, no es requisito para entrenar defectos.
5. Calibración de confianza, umbrales por clase y aprobación metodológica de uso operativo.
   Los experimentos binarios, de enfermedades y FGrade no sustituyen estas evidencias.
