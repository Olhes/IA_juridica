# Implementar el harness de evaluación de IA Jurídica

**Resultado:** Un harness reproducible que mide si el asistente alucina, si LightRAG recupera la jurisprudencia correcta, si la traducción español→quechua es confiable, si el stream NDJSON llega válido y a tiempo al frontend, y si un commit empeoró respecto de otro. Además expone al usuario final señales de confianza verificables.

**Norma de evaluación:** [`SAT-GRAPH-EVALUATION-PLAN.md`](SAT-GRAPH-EVALUATION-PLAN.md) manda. Este plan no la reemplaza; la aplica al pipeline v8:

- El gold lo etiquetan abogados con doble revisión ciega. Lo que genere el harness son **candidatos pendientes de revisión humana**, nunca verdad.
- Cuando el denominador de una métrica es cero se reporta `n/a`, no un 0 silencioso.
- Se reportan promedios macro (por caso/tema) y micro (por unidad).
- Los umbrales se **prerregistran después de medir un baseline**. Este plan no fija umbrales numéricos; solo prepara el mecanismo.
- Ningún modelo externo corre en CI de pull request. Las evaluaciones reales solo corren con `--run-model-evals`.

## Estado actual de v8 (verificado)

- **Pipeline único:** `backend/services/legal_queries.py:answer_query` hace recuperación, generación, validación y traducción, y se abstiene si no hay evidencia (`metadata.evidence_status`). Lo usan `/legal-query`, chat y `/legal-query-stream`.
- **Stream:** `/legal-query-stream` (`backend/main.py`, ~línea 637) ejecuta todo el pipeline antes de responder y emite un solo `chunk` + `final`. No hay tiempos por etapa (solo `validation.processing_time_ms`), ni contrato versionado, ni `seq`, ni códigos de error.
- **Frontend:** `frontend/src/application/legal/use-cases/useChat.ts:203` hace `JSON.parse(line)` sin `try`: una línea mala tira toda la respuesta.
- **Recuperación:** `lightrag_engine.py:query_with_rerank` usa `aquery_data(mode="mix")` + `_local_candidates`. Reserva la mitad del presupuesto para el grafo y luego aplica rerank de Cohere con un umbral mínimo de 0.1.
- **Traducción:** `translation_service.translate` traduce por segmentos y protege referencias con `ZXQREF`. Devuelve `success`, `complete`, `review_required` (siempre `True`) y `warning`. `legal_queries.py` pega `[Aviso: ...]` al texto traducido.
- **Caché:** `optimization/query_cache.py:answer_cache_key` incluye el `prompt_digest` del código del pipeline. `rag_engine.get_cache_revision()` da el hash del corpus.
- **Evaluación existente:** `backend/evaluation/model_quality.py` evalúa al generador con contexto controlado y un juez DeepEval (`EVAL_JUDGE_MODEL`, `OPENAI_API_KEY`). `tests/backend/fixtures/quality_cases.json` tiene solo 3 fichas ficticias. Ya existen las suites `tests/backend/{contract,http,bdd,benchmark,quality,security}`.
- **Pruebas de frontend:** vitest + msw + Playwright (`tests/frontend`).
- **Lo que falta en el frontend:** `types.ts` y `ChatMessage.tsx` no muestran `metadata.translation`, `evidence_status` ni `validation.is_reliable`.
- **Lo que no existe:** `.github/`.

## Arquitectura

```text
backend/evaluation/harness/
  runner.py            # orquesta suites, escribe resultados, registra metadatos
  pipeline_eval.py     # llama a answer_query real (sin HTTP)
  retrieval_eval.py
  translation_eval.py
  stream_eval.py
  compare.py           # comparación entre commits
  judges.py            # juez configurable; registra cuál corrió y si estuvo disponible
  cassettes.py         # graba y reproduce Cohere, rerank y Google
  metrics/             # evidence recall@k/precision@k (definición SAT), faithfulness,
                       # legal_factuality, citations, translation, latency
backend/services/
  pipeline_telemetry.py   # tiempos por etapa
  translation_qe.py       # calidad estimada de traducción
  citation_verifier.py    # verificación determinista de citas
tests/backend/fixtures/gold/
  legal_qa.v1.jsonl
  retrieval.v1.jsonl
  translation.v1.jsonl
  ndjson_broken/
tests/backend/harness/    # tests nuevos, offline con cassettes
```

**Modos nuevos en `scripts/run-tests.mjs`** (con scripts en `package.json`):

| Modo | Qué hace | Requisitos |
| --- | --- | --- |
| `harness` | Suites del harness, offline, con cassettes | Ninguno; entra en CI de PR |
| `harness-real` | Evaluación real contra proveedores | `--run-model-evals`; fuerza `EVAL_MODE=1` (temperatura 0, caché apagada, N=3 muestras) |
| `harness-compare` | Compara dos refs | `--base <ref> --head <ref>` |

**Resultados:** `temp/harness/<sha>/<suite>.json`, con: sha, `prompt_digest`, revisión del corpus, hash del gold, modelos, juez y disponibilidad del juez.

**Reglas transversales**

- Ninguna fase llama a Cohere, Google ni OpenAI sin autorización explícita del usuario. Los cassettes se graban solo con esa autorización.
- Después de cada fase corre `pnpm test` (offline) y debe pasar; se corrige lo que se rompa en `contract`, `http` o `security`.
- Un commit por fase, en español.
- Todo texto de interfaz va en `translations.ts`, en español y quechua, y los tipos nuevos en `types.ts`.
- Antes de crear rutas del frontend se lee `node_modules/next/dist/docs/` (ver `frontend/AGENTS.md`).
- El gold y la traducción requieren abogados y un hablante nativo: se entrega el esquema, el tooling y candidatos marcados como pendientes; **no** se presentan como verdad.

## Fases

Orden: F0 → F1 → F2, F3 y F4 → F5 → F6.

### F0. Contrato NDJSON v1 y tiempos por etapa

- Modelo Pydantic `StreamEvent` `{v: 1, seq, request_id, type}` con los tipos `meta | stage | chunk | final | error(code, retryable) | done`. Exportarlo a JSON Schema y a tipos TypeScript.
- `pipeline_telemetry` mide `translate_in`, `retrieval`, `generation`, `validation`, `translate_out` y `cache_hit`. `answer_query` recibe un `on_stage` opcional.
- El endpoint emite `meta` y `stage` mientras corre, y el texto solo cuando ya está validado (nunca borradores).
- La autorización y la conversación ajena (401/404) se validan **antes** de abrir el stream. Los fallos posteriores salen como `error` con `code` (`RETRIEVAL_UNAVAILABLE`, `GENERATION_UNAVAILABLE`, `TRANSLATION_UNAVAILABLE`, `TIMEOUT`).
- `final.data.metadata.timings` lleva los tiempos.
- Actualizar `tests/backend/contract/test_shapes.py`, `http/test_api.py` y `security`.
- **UI:** etapas en vivo ("Buscando en el corpus → Redactando → Verificando → Traduciendo"); "Respondió en X s" con desglose por etapa; errores según su `code`, con botón Reintentar.

### F1. Gold y métricas contra alucinaciones

- Esquema por caso: `id`, `topic`, `query`, `language`, `reference_segments`, `required_facts`, `forbidden_claims`, `acceptable_citations`, `must_abstain`, `stratum` (`positivo | limite | negativo`), `split` (`dev | holdout`), `reviewers`, `version`.
- Loader con validación estricta y unos 30 casos semilla extraídos de `backend/docs/processed/`, marcados `reviewers: []` y `status: "candidate"`. **No se inventa contenido jurídico:** cada hecho cita su segmento de origen.
- Métricas:
  - **Faithfulness:** diagnóstico; no decide el lanzamiento.
  - **Legal factuality:** recall de `required_facts` + afirmaciones prohibidas o sin respaldo.
  - **Precisión de citas:** determinista, regex Ley/art./Casación contra el corpus (`citation_verifier`).
  - **Abstención:** recall de abstenciones requeridas y tasa de abstención innecesaria.
  - **Calibración:** `confidence_score` contra la factuality.
- Primero se mide un baseline; **no se fijan umbrales numéricos**, solo queda preparado el mecanismo para prerregistrarlos.
- **UI:** panel "¿Por qué confiar en esta respuesta?"; chips de citas verificadas ✓ o ⚠ con el extracto de origen; tarjeta de evidencia insuficiente con recursos (Defensoría, CEM, Línea 100).

### F2. Recuperación de jurisprudencia

- Evaluar por separado: LightRAG puro en los modos `naive`, `local`, `global`, `hybrid` y `mix`; solo léxico; la mezcla actual; y el resultado después del rerank con umbral 0.1.
- Métricas: Recall@k y Precision@k de evidencia, MRR, nDCG, jurisprudence hit rate, tasa de `no_match` y de fallback, y cuánta evidencia relevante descarta el umbral.
- Regla `n/a` cuando el denominador es cero. Los chunks se mapean a segmentos gold con una regla de solapamiento documentada.
- **UI:** jurisprudencia relacionada, con su relevancia y el camino de recuperación.

### F3. Traducción es→qu

- Gold paralelo extraído de `Ley 30364 quechua-castellano` (está en `processed_backup`, no indexada), de los manuales Cusco-Collao y Chanka y del vocabulario. Se marca la variante de cada par y queda pendiente de revisión por un hablante nativo.
- Métricas: chrF++ (principal), BLEU y TER, round-trip con embeddings de Cohere, glosario, preservación de `ZXQREF`, language ID y cobertura.
- El `[Aviso: ...]` sale del texto: vive solo en `metadata.translation`.
- `translation_qe` agrega `metadata.translation.quality` (alta, media o baja).
- **UI:** badge de calidad del quechua + "Ver original en español" + aviso de revisión como componente.

### F4. QA del stream

- **Backend, `StreamGuard`:** valida el schema, garantiza un solo terminal + `done`, tiene un watchdog y verifica que `chunk` y `final` coincidan.
- **Frontend, `frontend/src/application/legal/stream/ndjsonParser.ts`** (función pura, test en `tests/frontend/unit/`): tolera BOM, CRLF y líneas partidas; repara o descarta y cuenta las líneas inválidas; deduplica y ordena por `seq`; si falta el `final`, usa el chunk y marca `degraded`; mide los tiempos. Se integra en `useChat`.
- **Telemetría:** `POST /telemetry/stream` recibe solo números y `request_id`, nunca texto.
- **Pruebas:** fixtures rotos con fuzzing en pytest y vitest, más Playwright con streams rotos. Se reporta latencia p50 y p95 por etapa.

### F5. Comparación entre commits

- `pnpm test:harness:compare --base v8 --head HEAD` crea un `git worktree` por ref y reutiliza los resultados si ya existen.
- El reporte incluye: delta por métrica (macro y micro) con IC por bootstrap pareado; comparación A/B ciega con orden invertido; casos que empeoraron o mejoraron; y si cambiaron `prompt_digest`, el corpus o el modelo.
- Veredicto `MEJORÓ`, `IGUAL` o `EMPEORÓ`. Bloquea ante afirmaciones nuevas sin respaldo en casos críticos.
- Salida en markdown y JSON.
- **UI:** feedback 👍/👎 con motivo → `POST /feedback` → cola de candidatos al gold; página `/calidad` con las métricas publicadas; `/calidad/admin` (rol admin) con regresiones y colas de revisión.

### F6. CI

- GitHub Actions: en cada PR, `pnpm test` + `test:harness` offline; cada noche o con la etiqueta `eval`, `harness-real` + compare.
- Actualizar `tests/README.md` (lo verifica `test_documentation_contract.py`).

## Funcionalidades visibles para el usuario final

Se implementan junto a la fase correspondiente. Textos en `translations.ts` (español y quechua) y tipos en `types.ts`.

| # | Funcionalidad | Fase |
| --- | --- | --- |
| 1 | Etapas en vivo ("Buscando en el corpus → Redactando → Verificando → Traduciendo") | F0 |
| 2 | Tarjeta de evidencia insuficiente con recursos (Defensoría, CEM, Línea 100) | F1 |
| 3 | Panel "¿Por qué confiar en esta respuesta?" | F1 |
| 4 | Chips de citas verificadas ✓ o ⚠, con el extracto de origen | F1 |
| 5 | Jurisprudencia relacionada, con su relevancia y el camino de recuperación | F2 |
| 6 | Badge de calidad del quechua + "Ver original en español" + aviso de revisión como componente | F3 |
| 7 | Errores según su `code`, con botón Reintentar | F0/F4 |
| 8 | "Respondió en X s" con desglose por etapa | F0 |
| 9 | Feedback 👍/👎 con motivo → `POST /feedback` → cola de candidatos al gold | F5 |
| 10 | Página `/calidad` con las métricas publicadas | F5 |
| 11 | `/calidad/admin` (rol admin) con regresiones y colas de revisión | F5 |

## Qué requiere humanos

| Artefacto | Quién | Estado en el repositorio |
| --- | --- | --- |
| Gold jurídico | Abogados, doble revisión ciega | Candidatos con `reviewers: []` y `status: "candidate"` |
| Gold de traducción | Hablante nativo de quechua | Pares marcados como pendientes de revisión |
| Umbrales de lanzamiento | Equipo, tras medir un baseline | Solo el mecanismo de prerregistro |
| Cassettes | Usuario autoriza la grabación | Se graban únicamente con su permiso |

## Estado de implementación

| Fase | Estado | Notas |
| --- | --- | --- |
| F0 | Hecha | Contrato NDJSON v1, tiempos por etapa y UI de etapas, errores y tiempos. |
| F1 | Hecha | Núcleo `backend/evaluation/harness/` (gold, métricas, jueces, cassettes, runner, umbrales), `citation_verifier`, 107 casos **candidatos** bilingües (80 es + 27 qu) y UI de evidencia insuficiente, panel de confianza y chips de citas. Pendiente de humanos: revisión ciega de abogados; baseline real (requiere autorización de red/coste). |
| F2 | Hecha | Evaluación por sistema (`retrieval_eval.py`), regla de solapamiento (`overlap.py`), `retrieval.v1.jsonl`, `trace` en `query_with_rerank` y UI de jurisprudencia relacionada. Los sistemas con LightRAG o Cohere solo se miden con `--run-model-evals` o desde un cassette (no grabado). |
| F3 | Hecha | 319 pares es→qu **candidatos** con su origen verificado (manuales cusco-collao y chanka, Ley 30364), chrF++/BLEU/TER y señales de contrato propios, `translation_qe` (calidad alta/media/baja), aviso fuera del texto y UI de calidad, aviso de revisión y "Ver original en español". El sistema real (Google) solo con `--run-model-evals` o cassette (no grabado). Pendiente de humanos: revisión de hablantes nativos. |
| F4 | Hecha | `StreamGuard` (servidor), `ndjsonParser.ts` puro integrado en `useChat`, `POST /telemetry/stream` y resumen admin, 15 streams rotos reproducibles con fuzzing en pytest y vitest, suite `stream` (p50/p95 por etapa) y Playwright con streams rotos (12 pruebas pasan con Edge). |
| F5 | Hecha | `harness.compare` (bootstrap pareado, A/B ciego, bloqueos, informe md/json, `git worktree` temporal con el harness actual), `pnpm test:harness:compare`, 👍/👎 → `POST /feedback` → cola de candidatos, `/calidad` y `/calidad/admin`. Verificado contra la historia real (`feature/harness-v8` → HEAD) con las suites offline. |
| F6 | Hecha | `ci.yml` y `harness-real.yml` (cuatro suites reales con juez Cohere: DeepEval y RAGAS). Los workflows no se pudieron ejecutar localmente: se validan con un test de contrato. |

Hallazgos que condicionan el resto del plan:

- La interfaz activa es `TerminalModal`; `ChatMessage.tsx` no se renderiza en ninguna página, por lo
  que las funcionalidades visibles se integran en la terminal.
- Cuatro de los documentos jurídicos más largos del corpus tienen OCR espaciado (más del 90 % de los
  tokens son una letra), lo que degrada su recuperación; F2 lo mide.
- Medición offline (`python -m evaluation.harness.runner retrieval`, gold aún `candidate`): el motor
  léxico local alcanza un recall de evidencia@5 macro de ~0,63; con el rerank de respaldo baja a ~0,58 y
  la jurisprudencia recuperada de ~0,83 a ~0,67. Las preguntas fuera del corpus siempre devuelven
  fragmentos: la abstención descansa por completo en el umbral del rerank.
- El índice de LightRAG está desfasado respecto del corpus procesado: 10 de los 50 segmentos del gold no
  los cubre ningún fragmento indexado (ningún modo puede recuperarlos), 210 de 759 fragmentos indexados no
  corresponden a ningún segmento y todos tienen `file_path: unknown_source` (la fuente se pierde).
- La heurística de idioma del resultado acierta en ~91 % de las referencias quechua y ~97 % de los
  originales en español del propio gold (frases de ≥ 4 palabras). La línea base "copiar el español"
  obtiene chrF++ macro ~0,09 y la estimación de calidad la marca `baja` en el 100 % de los pares.
- Los hablantes de la edición de la Ley 30364 no declaran la variante: el gold la marca
  `sureno-sin-confirmar`.
- `ChatPage.test.tsx` y el mock de Playwright estaban desfasados: el chat exige sesión y simulaban un visitante
  anónimo. Se corrigieron (usuario sintético por defecto). Playwright usa `PLAYWRIGHT_CHANNEL=msedge` si falta el
  Chromium que pide la versión instalada.
- Cuatro pruebas de `test_google_oauth.py` fallan en la base (v8) por mensajes de error que filtran detalle de
  la base de datos en el callback de Google; no se tocó el código de autenticación.
- Comparación real `feature/harness-v8` → `HEAD` (suites offline): `retrieval` y `translation` salen `IGUAL`
  (los cambios de F2 en el motor son solo instrumentación) y `stream` no existe en la base (sin contrato). El
  veredicto de `legal_qa` y los demás modelos reales requiere resultados de `harness-real`.
