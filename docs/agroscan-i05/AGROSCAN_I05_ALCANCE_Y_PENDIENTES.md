# AgroScan · Incremento 05 — Validación integral y cierre técnico

**Alcance:** integrar la evidencia de calidad V2, geometría 2D ArUco aproximada, identidad por evaluación/imagen, pesaje IoT, historial y revisión humana. Ejecutar pruebas automatizadas sin modificar el negocio, conservar las evidencias de las ejecuciones y declarar pendientes verificables.

## Matriz de aceptación

| Puerta | Verificación | Evidencia admisible | Estado inicial |
|---|---|---|---|
| S01 | Flujo y navegación I01 | Pruebas unitarias frontend y contrato de adquisición | Pendiente de ejecución I05 |
| S02 | Calidad V2 I02 | Dos vistas; propuesta experimental; discrepancia, sin modelo y errores | Pendiente de ejecución I05 |
| S03 | Dimensión aproximada I03 | Escala nominal 30 mm por imagen, etiquetas aproximadas y ausencia de falsa precisión | Pendiente de ejecución I05 |
| S04 | Historial I04 | Evidencias solo lectura vinculadas a ID, sin promediar ni mezclar periodos/evaluaciones | Pendiente de ejecución I05 |
| S05 | Integridad de fuente | SQLite solo lectura, hash previo/posterior sin modificación y diff-check | Pendiente de ejecución I05 |
| F01 | Pesaje físico end-to-end | ESP32/HX711 real → puente USB/serie/HTTP → FastAPI → peso pre/post → confirmación | **No acreditado** |
| F02 | Calidad validada externamente | Dataset independiente por producto/clase; sesión; etiquetas humanas; métricas | **No acreditado** |
| F03 | Exactitud dimensional | Regla/calibrador real; varias frutas y orientaciones; error e incertidumbre | **No acreditado** |
| F04 | Experiencia browser | Capturas fechadas de operador y revisor, listado e historial después de reiniciar | **Por completar** |

## Criterio de aceptación

- **Software aprobado:** I05 `--run` termina con código 0, las etapas reportan `passed` y SQLite permanece inalterada.
- **Cierre técnico condicionado:** documentación y automatizaciones completas, sin afirmar una validación del dispositivo real ni de la precisión de IA.
- **Cierre integral/piloto acreditado:** además del software, disponer de F01–F04 documentados. Sin esas pruebas, no atribuir uso productivo o certificado.

## Protocolo manual breve

1. Ejecutar I05 `--preflight` y `--run --evaluation E-000019` y conservar `AGROSCAN_I05_RESULTADOS.json`, informe y los logs.
2. En navegador, iniciar sesión como operador. Abrir evaluación con dos fotos; verificar V2 y cm aproximados automáticos. No anotar un peso inexistente.
3. Abrir `Historial → Detalle` para la misma evaluación; cotejar IDs, grados sugeridos y medidas de ambas fotos. Si una vista es no evaluable, confirmar que no se asignó un grado consolidado.
4. Iniciar sesión como revisor. Comprobar que la vista distingue propuesta automática de decisión humana, y que no puede registrar una clasificación definitiva sin procedimiento de revisión.
5. Solo si se dispone de hardware: capturar dos pesos **reales** vigentes, asociados al mismo dispositivo, pieza y evaluación; registrar comprobantes de API y pruebas de desconexión/lectura caducada.
6. Para validar precisión IA: cotejar E0/E1/E2 contra etiquetas humanas independientes, estratificadas por mango Kent/tomate. Registrar matriz de confusión, precisión, recall, F1 por clase y límites de generalización.
7. Para dimensión: contrastar eje mayor/menor óptico vs instrumento físico, con método de muestreo y repetibilidad, registrando errores por fruta y por vista.

## Limitaciones que no deben omitirse

- Los *scores* del clasificador V2 no son probabilidades calibradas y el entrenamiento no acredita desempeño independiente en entorno real.
- Los centímetros de I03 son una **escala óptica nominal** calculada con ArUco 30 mm; no corrigen altura 3D, distorsión óptica ni posición de la cámara. No son diámetros físicos certificados.
- La homografía A4 rigurosa puede seguir en `needs_review` sin afectar a la estimación aproximada; no confundir resultados o versiones.
- Las dos fotografías no sustituyen el peso inicial/final exigido para confirmar adquisición en FastAPI.
- Una etiqueta V2 concordante no equivale a un dictamen humano final.

## Texto para Jira (rellenar tras ejecutar)

> AGROSCAN · Incremento 05. Ejecutada la validación de software I01–I04 y regresión transversal I05; ver informe generado en `docs/agroscan-i05/runs/<ejecución>/AGROSCAN_I05_CIERRE_TECNICO.md`. Resultado de pruebas: **[pasaron/fallaron]**; registro SQLite: **[sin cambios / requiere investigación]**. La clasificación V2 es experimental, las dimensiones son proyecciones ópticas nominales y la confirmación de adquisición conserva los requisitos reales de peso. **Pendientes de acreditación:** integración física ESP32/HX711, desempeño independiente E0/E1/E2, exactitud dimensional y recorrido de navegador documentado. No se declara validación productiva.
