# Evaluar la recuperación jurídica peruana fundamentada en fuentes

**Decisión:** Un corpus peruano seleccionado y etiquetado por abogados es el principal benchmark de lanzamiento. Los benchmarks externos de recuperación y los evaluadores automatizados son diagnósticos, no pruebas de vigencia temporal. Consulte el [plan de implementación](SAT-GRAPH-IMPLEMENTATION-PLAN.md) para conocer el orden de migración.

## Qué puede medirse actualmente

| Etapa | Evidencia disponible | Afirmación aún no sustentada |
| --- | --- | --- |
| Segmento actual | Hashes de PDF/Markdown, un ID de evidencia inmutable para carga y procesamiento por lotes, procedencia no verificada | Origen oficial, unidades jurídicas, fechas, escritura en el grafo o segmentos de origen |
| RAG heredado | Documentos/fragmentos locales y grafo de entidades inferido; `add_document` puede recurrir al almacenamiento local | Confirmación exitosa en el grafo jurídico o recuperación correcta de la ley vigente a una fecha |
| Fases posteriores | Segmentos de origen revisados, hechos tipados Work/CTV/CLV/Action, recuperación por fecha | Solo después de superar los criterios de aprobación de fuentes, seguridad y conciliación |

No utilice `backend/evaluation/deepeval_tests.py` como criterio de aprobación para el lanzamiento: cuando DeepEval no está disponible, ejecuta una **alternativa simulada basada en palabras clave**. Registre qué evaluador se ejecutó; no instale paquetes ni invoque modelos externos en CI.

## Conjunto de referencia principal: legislación peruana seleccionada por abogados

1. Obtener publicaciones oficiales con condiciones de acceso y redistribución registradas; almacenar la URL oficial/referencia de publicación, licencia, fecha de acceso, bytes del PDF y SHA256. El nombre de archivo cargado, la categoría o un título inferido **no** son un localizador oficial.
2. Para cada instrumento, registrar jurisdicción, alcance, identificador oficial de Work, ruta del componente y pertenencia a su padre; identificar por separado edición e idioma. Almacenar de manera independiente las fechas de publicación, promulgación, entrada en vigor y finalización, mediante intervalos semiabiertos `[start, end)`; las fechas desconocidas o controvertidas permanecen desconocidas.
3. Los abogados etiquetan la versión CTV respaldada por la fuente y la revisión de texto CLV, las Actions de modificación/derogación (fuente, versiones terminadas y producidas), la cadena causal exacta y los desplazamientos de página + carácter/segmento respecto de la fuente con hash/transcripción verificada. Conservar el mapeo de desplazamientos entre fuente y Markdown, la revisión de anotaciones y los IDs de los revisores.
4. Etiquetar para cada pregunta la fecha de consulta, jurisdicción, alcance aplicable, segmentos de referencia mínimos, respuestas obligatorias/prohibidas, citas aceptables y si la abstención es obligatoria. Conservar varios segmentos de referencia no contiguos cuando sea necesario.
5. Dos revisores jurídicos independientes resuelven las discrepancias sin conocer los resultados del sistema; registrar el fundamento, la resolución y la revisión de referencia reemplazada. Poner en cuarentena la autoridad ambigua en vez de convertir la inferencia de un analizador en verdad de referencia.

Estratificar los casos positivos entre reutilización de hijos sin cambios, pertenencia de artículos anidados, modificación parcial, derogación, efecto diferido, retroactividad, reglas de alcance en competencia y tablas. Incluir casos negativos y de límite: día anterior/al inicio/al final de la vigencia, fecha ausente, fuente oficial faltante, ediciones en conflicto, segmento faltante, jurisdicción extranjera, alcance incorrecto y consulta no respondible. Mantener intacto un conjunto reservado.

## Protocolo de comparación

- Comparar la ruta de recuperación heredada sin cambios, una línea base opcional de solo texto con configuración equivalente y una futura ruta tipada/temporal en sombra; todavía no existe ningún sistema en sombra.
- Fijar los bytes/hash del corpus, la revisión de referencia, la política de elegibilidad, el conjunto de consultas, las versiones del modelo/prompt, `top-k`, el presupuesto de tokens de contexto y la semilla aleatoria antes de la evaluación. Mantener constantes el hardware, la concurrencia, la política de caché y la fecha de consulta.
- Separar por familia normativa **y linaje/tiempo de modificación**: las ediciones relacionadas, los pasajes casi duplicados y las variantes de un instrumento no deben cruzar los límites entre ajuste y conjunto reservado. Las etiquetas de referencia y los segmentos esperados no deben incorporarse a los prompts, embeddings, reescritura de consultas ni metadatos de recuperación durante la ejecución de prueba.
- Ejecutar comparaciones pareadas por pregunta con el mismo presupuesto; declarar que la ruta heredada carece de selector temporal en lugar de asignarle uno implícitamente. Informar denominadores brutos, resultados estratificados, incertidumbre y casos de fallo, no afirmar mejoras antes de medirlas.

## Métricas principales (definir la unidad antes de puntuar)

Sea `G(q)` el conjunto de IDs distintos de disposiciones/segmentos aprobados por abogados para la consulta respondible `q`, y `R_k(q)` los IDs distintos devueltos dentro del `top-k` fijo. Mapear fragmentos heredados a segmentos de referencia solo mediante una regla de solapamiento documentada y conservar los IDs sin correspondencia. Si el denominador es cero, informar **n/a**; nunca asignar silenciosamente una puntuación de 0 o 1.

| Métrica | Numerador / denominador | Interpretación |
| --- | --- | --- |
| Recuperación de evidencia@k | `|R_k ∩ G| / |G|` para consultas respondibles | Unidades de respaldo necesarias que faltan |
| Precisión de evidencia@k | `|R_k ∩ G| / |R_k|` | Las unidades irrelevantes o de una versión incorrecta cuentan como fallos |
| Versión correcta | Preguntas respondibles contestadas con todas las versiones afirmadas elegibles en la fecha/alcance solicitados / total de preguntas respondibles | Abstenerse ante una pregunta respondible cuenta como fallo; informar por separado las afirmaciones de versión incorrecta |
| Tasa de versión incorrecta | Preguntas contestadas que afirman cualquier versión no elegible / preguntas contestadas | Fallo de seguridad, no simplemente una puntuación baja de recuperación |
| Coincidencia exacta de cadena causal | Actions revisadas con enlaces exactos y ordenados de origen/terminado/producido / cadenas de Action evaluadas | Las cadenas parciales o inventadas fallan; n/a actualmente |
| Precisión de segmentos citados | Segmentos afirmados como cita que coinciden con los desplazamientos de la fuente oficial de referencia / total de segmentos afirmados como cita | Las citas que solo indican nombre de archivo/documento no coinciden |
| Recuperación de segmentos citados | Segmentos de referencia requeridos citados por una respuesta / segmentos de referencia requeridos para las preguntas contestadas | Debe cubrirse el respaldo de varios segmentos |
| Pertenencia estructural | Pares componente-padre vinculados correctamente / pares componente-padre evaluados | Disposiciones anidadas, hijos reutilizados; n/a actualmente |
| Afirmaciones jurídicas sin respaldo | Afirmaciones incorrectas o sin respaldo señaladas por abogados / total de afirmaciones sustantivas de respuestas | Contar fechas, alcances y atribuciones falsas |
| Recuperación de abstenciones requeridas | Abstenciones correctas / preguntas de referencia que requieren abstención | Las respuestas seguras pero incorrectas fallan |
| Tasa de abstención innecesaria | Abstenciones ante preguntas respondibles / preguntas respondibles | Informar la cobertura como preguntas respondidas / total de preguntas |

Informar por separado los valores macro por pregunta y los numeradores/denominadores micro; no permitir que una ley extensa domine el resultado. Usar coincidencia exacta para los enlaces causales e incluir un diagnóstico separado de relaciones parciales. Nunca inferir citas a partir del título de un documento. Auditar una muestra de todos los errores de afirmaciones, no solo de las oraciones generadas.

## Funciones de los marcos y validez externa

| Recurso | Función útil | Límite |
| --- | --- | --- |
| Artículo de [LegalBench-RAG](https://arxiv.org/html/2408.10343v1) y [repositorio](https://github.com/zeroentropy-ai/legalbenchrag) | Prueba secundaria de estrés para recuperación de segmentos exactos; los documentos incluyen etiquetas de rangos de caracteres | Principalmente contratos/políticas de privacidad, no legislación peruana temporal; en su corpus hay un documento por pregunta. El resumen y la tabla del artículo discrepan en el total de consultas: no utilice esos recuentos. Verifique las licencias del conjunto de datos antes de usarlo. |
| [Precisión de ID de Ragas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/) / [recuperación de ID](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/) | Comprobación determinista opcional de solapamiento de IDs mediante `retrieved_context_ids` y `reference_context_ids` en `SingleTurnSample`; **no requiere LLM** | La concordancia de IDs requiere IDs de referencia con la granularidad jurídica adecuada; no determina la autoridad oficial ni las fechas. |
| [Fidelidad de Ragas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) | Diagnóstico secundario de la respuesta respecto del contexto recuperado | Ser fiel a un contexto obsoleto o no oficial sigue siendo jurídicamente incorrecto; los resultados del evaluador requieren auditoría humana. |
| [Conjuntos de datos de DeepEval](https://deepeval.com/docs/evaluation-datasets) / [fidelidad](https://deepeval.com/docs/metrics-faithfulness) | Organización secundaria de conjuntos de prueba/casos de prueba y evaluación del contexto | Su fidelidad utiliza `input`, `actual_output`, `retrieval_context`; no sustituye la adjudicación basada en fuentes oficiales fechadas. |

Si se utiliza un evaluador LLM, fijar el modelo/prompt/modalidad de evaluación, muestrear juicios entre estratos positivos, negativos y limítrofes, y pedir a abogados sin conocimiento previo que marquen falsos positivos/negativos del evaluador. Informar las discrepancias y su resolución; nunca usar por sí sola la puntuación de fidelidad del evaluador para decidir el lanzamiento.

## Fases y criterios de aprobación prerregistrados

| Fase | Trabajo | Criterio antes de avanzar |
| --- | --- | --- |
| 1 — ahora | Pruebas sin conexión de ID de evidencia, duplicados/reinicio, alteración, fallos y paridad entre carga/procesamiento por lotes | IDs estables; ningún registro ante fallos de conversión/escritura; ninguna escritura RAG ante fallo del almacén de evidencia |
| 2 — revisión de fuentes | Verificar corpus/licencia oficiales; adjudicar segmentos, versiones, alcances, vínculos estructurales y Actions | Los revisores aprueban la revisión de referencia; se superan las comprobaciones de recorrido de ida y vuelta de fuente y desplazamientos |
| 3 — sombra | Ejecutar experimentos pareados de recuperación y respuesta con parámetros bloqueados; auditar evaluación y conciliación | Los responsables jurídicos y de operaciones prerregistran los umbrales **antes** de la ejecución con el conjunto reservado |
| 4 — lanzamiento | Revisar errores del conjunto reservado, aislamiento de autorización, recuperación, costo y demora medida | Bloquear ante acceso no autorizado, respuesta afirmada con versión incorrecta o relación jurídica afirmada sin trazabilidad; flag de reversión probada |

Para la carga operativa, informar la latencia p50/p95 por consulta (recuperación y extremo a extremo), el costo de tokens/API y la tasa de errores por consulta, además del tiempo de ingesta por PDF y la demora entre confirmación y conciliación p50/p95, junto con los recuentos de trabajos pendientes/fallidos. Declarar el hardware, tamaño de muestra, concurrencia y estado de caché. No afirmar mejoras numéricas ni objetivos sin una comparación observada y prerregistrada.

## Plantilla de informe

| Campo | Entrada requerida |
| --- | --- |
| Ejecución | Fecha; hashes y revisión del corpus/referencia; particiones; política, prompt/modelo, semilla, k, presupuesto |
| Comparador | Heredado/solo texto/en sombra; entorno de ejecución; disponibilidad del evaluador y modalidad del evaluador |
| Calidad | Cada numerador/denominador, n/a, macro/micro, estratificación, intervalo de confianza |
| Seguridad | Versiones incorrectas, afirmaciones sin respaldo, segmentos/relaciones faltantes, abstención, discrepancias de revisión ciega |
| Operaciones | Latencia de consulta p50/p95, costo/consulta, tiempo de ingesta, demora de conciliación y trabajos pendientes |
| Decisión | Criterios prerregistrados, responsables, casos bloqueados, prueba de reversión y seguimiento |
