# Pipeline de validación — v8

Actualización: **2026-10-06**. Describe código ejecutado, no garantías jurídicas.

## Flujo común antes de entregar contenido

`services/legal_queries.py:answer_query` centraliza consultas JSON, NDJSON y chat:

1. Comprobar disponibilidad del corpus y caché exacta con revisión/propietario.
2. Traducir consulta quechua si corresponde; fallo de traducción de consulta: 503.
3. Recuperar documentos y rerankear; fallo de retrieval: 503.
4. Construir contexto con historial acotado y generar en español con Cohere.
5. Validar y, si corresponde, intentar corrección; usar la respuesta final validada.
6. Traducir salida si se solicita quechua, conservando advertencias de incompletitud.
7. Entregar JSON o contenido final por NDJSON; persistir en el flujo de chat/stream.

No se emiten borradores provisionales por `/legal-query-stream`.
`answer_query` mide cada etapa (`services/pipeline_telemetry.py`) y entrega `metadata.timings`; el stream NDJSON v1 las anuncia en vivo ([contrato](../API_DOC.md)).
Sin documentos: abstención explícita, fuentes vacías, `is_reliable=false`.
La corrección no debe fabricar asesoría cuando falta evidencia.

## Componentes

| Archivo bajo `modules/validation/` | Responsabilidad / límite |
|---|---|
| `services/schemas.py` | Respuesta e informe estructurados |
| `services/anti_hallucination.py` | Patrones heurísticos de riesgo; no prueba falsedad/verdad jurídica |
| `services/cross_checker.py` | Contraste de afirmaciones con corpus, no certificación de autoridad/vigencia |
| `services/self_correction.py` | Intentos acotados de corrección con proveedor; pueden consumir API |
| `services/response_validator.py` | Orquestación, fiabilidad, fuentes e informe final |

`main.py` configura umbral de riesgo desde `EVALUATION_THRESHOLD` (0.7 por
defecto), cross-check 0.55 y confianza mínima 0.30. No cambies umbrales para
mejorar un score sin validar un dataset independiente. Un score no es un porcentaje
de exactitud jurídica. Cantidad de chunks depende del corpus cargado, no de 707 fijos.

## Inspección segura

`GET /validation-stats`: admin habilitado y `X-API-Key`; muestra configuración,
RAG y estadísticas del optimizador. No es un endpoint público ni una evaluación
offline del generador. `GET /health` informa presencia de componentes, `/ready`
confirma estado del corpus. Evidencias de ingesta `unverified` siguen sin acreditar
autoridad oficial ni una fecha de vigencia.

## Pruebas ≠ evaluación de calidad

Las pruebas unitarias/HTTP usan datos sintéticos y dobles de proveedores para
comprobar código, errores y contratos. Se ejecutan con `pnpm test` desde raíz.
El chunker se prueba sin RAGAS porque sus invariantes son deterministas.

Para decidir qué chunking mejora el RAG se necesita un benchmark comparativo:
documentos/preguntas con referencias, pipeline real de retrieval y métricas como
Context Precision/Recall de RAGAS. No está implementado por añadir unitarios.
Los casos reales actuales usan DeepEval y el generador, con opt-in explícito
`pnpm test:quality --run-model-evals`; tampoco acreditan por sí solos todo el RAG.
[Guía única y catálogo](../tests/README.md).
