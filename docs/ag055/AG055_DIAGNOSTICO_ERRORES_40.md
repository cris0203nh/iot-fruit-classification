# AG-055: diagnóstico de errores antes de modificar los modelos

Se analizaron las 40 etiquetas atribuidas a Junior Pérez, 13/11/2026, las imágenes originales y las 117 fotografías del piloto. Se ejecutaron inferencias, perturbaciones diagnósticas y análisis de distancias, sin entrenar, cambiar parámetros, corregir etiquetas ni tocar SQLite. Los resultados siguen siendo exploratorios; independencia física y variedad Kent no acreditadas.

## Conclusión técnica

Hay dos problemas distintos: **fragilidad demostrada del descriptor global y su escalado**, especialmente en tomate, y **confusión entre condiciones de adquisición, categorías originales y gravedad E0/E1/E2**. No se encontró una causa única para los 24 errores. Las etiquetas tienen discrepancias visuales que requieren interpretación de una rúbrica, no una corrección automática.

En tomate se localizó un mecanismo concreto: matices de baja saturación del fondo tienen varianza casi nula en entrenamiento; StandardScaler los amplifica y el kernel RBF deja de encontrar semejanza con los soportes. Entonces predominan los interceptos y la predicción tiende a E2. El modelo no dispone de una representación explícita de lesiones ni de un rechazo de entradas fuera de distribución. En mango, el aspecto global, el encuadre y la definición de E0 explican indicios importantes, pero no hay una atribución causal completa por foto.

## Matrices, desbalance y errores

Filas humanas, columnas predichas, orden E0/E1/E2:

```text
Mango, n=20                 Tomate, n=20
       E0 E1 E2                    E0 E1 E2
E0      0  5  3             E0      1  1  7
E1      2  7  2             E1      0  0  1
E2      0  1  0             E2      0  2  8
```

Mango: 7/20 aciertos, F1 macro 0,1944; falla todo E0 y el único E2. Tomate: 9/20, F1 macro 0,2718; predice E2 en 16/20 y solo reconoce 1/9 E0. Mango tiene 8/11/1 etiquetas humanas por clase y tomate 9/1/10: E2 mango y E1 tomate no admiten conclusiones estables con un solo caso.

El entrenamiento está casi equilibrado: mango 20/20/21 y tomate 20/17/19; el SVC ya usa ponderación balanced. Por tanto, cambiar pesos de clase no es la primera corrección justificada. El ajuste sobre las propias imágenes de entrenamiento reconoce 61/61 mango y 56/56 tomate: es resustitución, no validación ni prueba de independencia. Contrasta con el bajo rendimiento exploratorio y es compatible con sobreajuste o cambio de distribución.

Las siguientes observaciones son inspección visual del asistente y diagnóstico del código, **no nuevas etiquetas humanas ni diagnósticos fitopatológicos**. H→P indica etiqueta humana y predicción. La justificación humana íntegra se conserva en el JSON privado.

| Foto | H→P | Observación y mecanismo a comprobar |
|---|---|---|
| F008 mango | E2→E1 | Mancha central; el revisor menciona humedad. Gravedad local diluida por descriptor global y reducción a 96×96. |
| F010 mango | E0→E1 | Marca puntual y caja de fondo; falta criterio para distinguir marca tolerable de lesión. |
| F018 mango | E0→E1 | Pequeña zona oscura y otro fruto parcial; encuadre y límite E0/E1 ambiguos. |
| F019 mango | E1→E2 | Varias zonas oscuras; falta medida común de extensión/gravedad frente a entrenamiento. |
| F021 mango | E1→E0 | Mancha visible sobre fondo limpio; descriptor vecino de un Healthy E0, aunque eso no prueba identidad. |
| F022 mango | E0→E2 | Marcas oscuras visibles pese a justificación «sin nada»; discrepancia que no autoriza cambiar la etiqueta. |
| F023 mango | E0→E1 | Marca puntual visible, color rojizo y caja; mismo problema de criterio E0/E1. |
| F028 mango | E0→E2 | Zona central oscura; frontera de gravedad no documentada. |
| F032 mango | E1→E2 | Zona oscura superior y cambios de color/brillo; representación sin localización de lesión. |
| F034 mango | E0→E1 | Marca superior y fruto adyacente recortado; confusión entre objeto y contexto. |
| F036 mango | E1→E0 | Marcas visibles sobre fondo blanco; también vecino de un Healthy E0. |
| F037 mango | E0→E2 | Varias marcas visibles pese a «sin nada»; posible desacuerdo de criterio, sin reetiquetar. |
| F039 mango | E0→E1 | Marcas visibles y caja; definición de tolerancia E0 no acreditada. |
| F002 tomate | E0→E2 | Fruto aparentemente íntegro sobre papel; histograma cromático aporta 85,2 % de distancia al soporte más cercano. |
| F006 tomate | E0→E2 | Fruto aparentemente íntegro; similitud RBF numéricamente cero y variación de matiz en sombra/fondo. |
| F009 tomate | E0→E2 | Tres frutos, frente a entrenamiento principalmente individual; RBF cero. |
| F012 tomate | E1→E2 | Revisor menciona hoja/cáliz; señal localizada, RBF cero. |
| F015 tomate | E2→E1 | Arrugamiento y zona localizada; imágenes semejantes del entrenamiento están declaradas E1. |
| F016 tomate | E0→E1 | Fruto anaranjado sobre superficie de madera, contexto asociado a Rotten en entrenamiento. |
| F017 tomate | E0→E2 | Dos frutos y papel muy claro; RBF cero, histograma cromático domina la distancia. |
| F024 tomate | E0→E2 | Fruto aparentemente íntegro; brillo/fondo, RBF 1,12×10⁻²². |
| F026 tomate | E0→E2 | Tres frutos sobre papel; RBF cero. |
| F031 tomate | E0→E2 | Caso más claro de amplificación de matiz del fondo: dimensión 635 aporta 98,46 % de distancia. |
| F040 tomate | E2→E1 | Defecto localizado y arrugamiento; frontera E1/E2 no consistente visualmente entre conjuntos. |

Los otros 16 casos coinciden con la etiqueta recibida; esa coincidencia tampoco acredita razonamiento por defectos. El detalle reproducible de los 40 casos está en `diagnosis.json`.

## Fondo, luz, encuadre y características

El descriptor actual tiene 676 componentes: 576 píxeles de gris a 24×24 (85,2 % de componentes), 96 componentes de histogramas RGB/HSV y cuatro estadísticas globales. Se calcula sobre **toda la imagen**, sin máscara ni ROI de fruta verificada. No mide área de lesión, textura localizada ni número de frutos. El recuento de dimensiones no equivale por sí solo a importancia causal.

Se aplicaron las mismas operaciones prefijadas a cada imagen, sin buscar la transformación que acierte más. Se cuentan cambios de etiqueta respecto al original, no mejoras de accuracy:

| Intervención diagnóstica | Mango, de 20 | Tomate, de 20 |
|---|---:|---:|
| Brillo ×0,75 | 9 | 4 |
| Brillo ×1,25 | 6 | 4 |
| Escala de grises | 3 | 3 |
| Sustituir borde exterior del 15 % por gris | 7 | 4 |
| Ocultar rectángulo central del 70 % conservando periferia | 5 | 4 |
| Añadir margen gris del 20 % por lado conservando todos los píxeles originales | 7 | 4 |
| Ablación del bloque gris espacial, reemplazado por media de entrenamiento | 15 | 4 |
| Ablación de histogramas, reemplazados por media de entrenamiento | 2 | 0 |

Las modificaciones pueden estar fuera de distribución; borde y periferia pueden contener fruta. **No son segmentación acreditada ni permiten afirmar que el fondo sea la causa exclusiva.** Una ablación sin cambio de etiqueta tampoco demuestra irrelevancia: el resultado puede quedar dominado por los interceptos. Añadir margen conserva los píxeles originales, pero cambia su escala al redimensionar.

### Mecanismo numérico localizado en tomate

En F006, F009, F011, F012, F017, F024, F026 y F031, el máximo kernel frente a cualquier soporte es menor que 10⁻⁶; siete son errores y F011 un acierto E2. Este valor es una descripción, **no un umbral operativo propuesto**. Las tres decisiones OVO tienden a los interceptos negativos (−0,2015; −0,2154; −0,3111), dando la mayoría a E2 incluso sin evidencia de una lesión.

En F031, el histograma de color aporta 99,9978 % de la distancia al soporte más cercano. La dimensión 635, bin 11 del matiz HSV (índice desde cero), aporta 98,46 %. Su escala entrenada es 0,00003712; pequeñas diferencias cromáticas se convierten en grandes distancias estandarizadas. En F006, el color aporta 99,71 % y esa dimensión 94,22 %.

Se localizaron visualmente esos píxeles en `hue_background.png`: en F031, 4330/9216 píxeles de la imagen reducida pertenecen a los bins de matiz 11/12 y todos tienen saturación menor que 32; predominan en el papel del fondo. En F006 son 364 píxeles, 96,4 % con baja saturación; aparecen principalmente alrededor de sombra y fondo. F014 no tiene píxeles en esos bins. En zonas casi acromáticas, un pequeño cambio RGB puede cambiar mucho el matiz sin representar un defecto. El descriptor cuenta ese matiz indiscriminadamente.

Esta evidencia localiza una dependencia espuria concreta de fondo/iluminación y su amplificación matemática. No demuestra que todos los errores ni todo el modelo se expliquen por ese mecanismo. No se hicieron sustituciones de valores para escoger una nueva versión con estas 40 fotos.

## Procedencia, etiquetas y relaciones

- **Mango:** los E0 de entrenamiento son 20 Healthy; E1 son 20 Alternaria; E2 combina 9 Alternaria y 12 Rotten. Los 20 mangos de evaluación son Alternaria de origen, pero Junior declaró 8 E0, 11 E1 y 1 E2. La categoría original no es verdad E0/E1/E2: esta diferencia muestra confusión de muestreo y frontera de etiquetas. Los Healthy incluyen muchos mangos verdes sobre fondo limpio, y Alternaria/Rotten suelen mostrar cajas, otros frutos y color amarillo/rojizo. No hay contrabalanceo que separe esas variables.
- **Tomate:** E0 entrenamiento = 20 Fresh; E1 = 17 Rotten; E2 = 19 Rotten. Las hojas de contacto muestran E0 principalmente sobre papel y E1/E2 sobre madera; E1 y E2 contienen frutos arrugados visualmente parecidos. Junior considera E2 todas las diez fotos Rotten de evaluación, incluida apariencia arrugada que en entrenamiento también recibe E1. F012, cuyo motivo es el cáliz, es el único E1 evaluado. Falta una regla común explícita para piel, cáliz, deshidratación y gravedad. No se puede concluir que un anotador esté equivocado sin esa regla.
- Cada producto procede de un solo dataset en este piloto: no se puede medir generalización entre datasets por producto. La confusión demostrable es con subcategorías, condiciones y sesiones de adquisición dentro de esas fuentes.
- En entrenamiento hay 59 componentes técnicos de mango y solo cuatro de tomate. Todos los E0 tomate quedan en un componente; otros componentes mezclan E1/E2. Son agrupaciones conservadoras, no identificaciones físicas. El tamaño efectivo de muestra y la partición independiente por clase siguen sin acreditarse; dividir fotografías al azar sería engañoso.
- Se preservaron las 117 declaraciones originales y las 40 etiquetas de Junior. Una marca visible no acredita enfermedad ni exige automáticamente E1/E2; las observaciones son conflictos que deben resolverse con la rúbrica existente, en el flujo humano ya disponible, sin formularios nuevos.

### F014

F014 corresponde a `TQ_001517`, nombre fuente `20230105_124633.jpg`. Su relación perceptual es con `pilot117_00f307fc985211e52db4`, fuente `TQ_001690`, `20230104_121716.jpg`, E0 de entrenamiento. Los hashes de bytes y píxeles son distintos; distancia perceptual mínima 8/63. La comparación visual muestra composición y fondo semejantes, pero distinto color del fruto. Eso puede explicar la similitud sin demostrar ni descartar que sea la misma fruta.

Los nombres sugieren días diferentes, pero no son registros de captura autenticados ni prueban independencia física. No hay identificación documental de fruta/sesión. La relación queda sin resolver; F014 no debe contarse como independencia acreditada. Es el único acierto E0 tomate, con máximo kernel 0,651; su clase cambia a E2 con brillo ×0,75, ×1,25, borde gris o margen añadido. Excluirla deja accuracy 42,11 % y F1 macro 0,2051; se conserva como sensibilidad descriptiva, sin elegir el resultado favorable.

## Corrección mínima recomendada y cómo comprobarla

**No cambiar el SVC desplegado, sus umbrales ni el preprocesamiento a sus espaldas.** Cualquier cambio de descriptor rompe el contrato con los soportes y el escalado existentes. No se justifica ahora aumentar C, cambiar gamma, añadir clases o hacer búsqueda de pesos.

1. **Primer cambio técnico a ensayar en una versión separada del mismo algoritmo:** excluir el fondo del descriptor mediante ROI/máscara de fruta comprobable; calcular el histograma de matiz solo en píxeles cromáticos de esa ROI y evitar amplificar dimensiones de varianza casi nula. Mantener normalización de tamaño por fruta y registrar fallos de máscara o múltiples frutos para revisión. La regla de saturación, eliminación de dimensiones o piso de escala se fija con entrenamiento/validación de desarrollo, nunca con estas 40. No se propone un valor numérico aprendido de los errores observados. Si no puede obtenerse una ROI fiable, mantener revisión humana, sin forzar una clase.
2. **Antes de entrenar esa versión:** armonizar con la rúbrica existente los conflictos ya localizados, preservando originales y añadiendo correcciones humanas solo cuando existan. E0 no puede ser un sinónimo de Healthy/Fresh, ni E2 de Rotten. Incluir variación de color, fondo y sesión dentro de cada clase; para mango, cubrir E0 con apariencias distintas a los Healthy actuales. El parche numérico por sí solo no resuelve esa carencia semántica/de cobertura.
3. **Desarrollo:** mantener las 40 como diagnóstico ya consultado; no reutilizarlas para elegir hiperparámetros, máscaras, umbrales ni como prueba final. Separar por fruta física y sesión todo el material de desarrollo, agrupar relaciones perceptuales sin resolver y evitar fuga entre particiones. Las cuatro agrupaciones técnicas actuales de tomate no bastan para acreditar una partición por clase; no inventar una partición independiente donde falte soporte.
4. **Pruebas técnicas previas:** comprobar máscara y píxeles conservados, imágenes sin fruta, varios frutos, brillo, exposición, fondos intercambiados con el mismo fruto conservado y reencuadre. Fijar el protocolo antes de medir; registrar cambios de etiqueta y distancia, no buscar la transformación que mejora las 40. Verificar ausencia de distancias dominadas por bins casi constantes y comportamiento explícito ante entradas ajenas al desarrollo. Estas comprobaciones no sustituyen la prueba de clasificación.
5. **Comprobación de mejora:** congelar versión, descriptor y reglas después de desarrollo. Comparar modelo anterior y candidato sobre las mismas fotografías nuevas, con etiquetas humanas fijadas antes de inferir y fruta/sesión separadas del entrenamiento. Contrabalancear fondo, iluminación, madurez y encuadre por producto/clase; dejar el tamaño y el criterio de mejora predefinidos, con soporte suficiente para cada clase. Medir matriz, precisión/recall/F1 por clase, F1 macro y accuracy; informar incertidumbre con remuestreo por fruta/sesión solo si esas unidades están acreditadas. Comprobar especialmente E0→E2 tomate y E2→E0/E1 mango. Afirmar mejora únicamente si supera el criterio fijado sin degradación crítica de clases; con muestra insuficiente, mantener resultado exploratorio.

No se han recogido mediciones manual/asistido y no se afirma ahorro de trabajo. Kent continúa pendiente. AGROP-67 permanece abierto.

## Evidencia y ejecución

Único informe nuevo de esta fase. Código de diagnóstico: `vision/ag055/diagnose40.py`. Evidencia privada: `C:\Users\Luigi\Documents\AgroScan_AG055_Diagnostico_40_03`, con `diagnosis.json`, hojas de contacto de las 157 fotografías, comparación F014 y localización de matiz del fondo. Las imágenes derivadas son ayudas diagnósticas; los originales permanecen intactos. Se verifican por SHA-256 los modelos congelados y los archivos protegidos antes y después.

Desde la raíz del repositorio; usar una salida privada nueva:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend\.venv\Lib\site-packages"
$env:PYTHONUTF8 = "1"
py -3.13 -m vision.ag055.diagnose40 `
  --evaluation "$env:USERPROFILE\Documents\AgroScan_AG055_Evaluacion_Exploratoria_40_20261113_01" `
  --pilot "$env:USERPROFILE\Documents\AgroScan_AG055_E0E1E2_117_01" `
  --package "$env:USERPROFILE\Documents\AgroScan_AG055_Revision_Ciega_40_02" `
  --output "$env:USERPROFILE\Documents\AgroScan_AG055_Diagnostico_40_04"
```
