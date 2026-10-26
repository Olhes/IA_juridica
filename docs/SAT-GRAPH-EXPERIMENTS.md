# Medir recuperación SAT sin confundirla con calidad jurídica

Existe una ruta **experimental administrativa**, independiente del chat LightRAG,
para comparar recuperación temporal, BM25, metadatos, embeddings Voyage y dos
adaptaciones de grafo/jerarquía. No hay transición de producción ni un corpus
jurídico aprobado. Los textos del primer experimento son inventados.

**Actualización 11/10/2026:** ya existe también un
[ensayo documental de PDF oficiales](#ensayo-documental-con-pdf-oficiales-11102026),
sin NotebookLM. La segmentación natural mejoró cobertura de referencias sin API;
no convierte el ensayo en aprobación jurídica ni migra el chat legado.

## Ruta rápida

Desde `D:\Web\IA_juridica`, generar un dataset congelado y ejecutar offline:

```powershell
.venv\Scripts\python.exe -X utf8 tests/backend/fixtures/sat_experiment.py temp/sat-experiments/dataset-v1.json
.venv\Scripts\python.exe -X utf8 backend/research/sat_benchmark.py temp/sat-experiments/dataset-v1.json --output temp/sat-experiments/offline-new.json --repetitions 3
```

Los archivos se crean exclusivamente: elegir nombres nuevos si ya existen.
Para la API real, guardar `VOYAGE_API_KEY` en `backend/.env`, **nunca en Git/chat**:

```powershell
.venv\Scripts\python.exe -X utf8 backend/research/sat_benchmark.py temp/sat-experiments/dataset-v1.json --output temp/sat-experiments/voyage-new.json --voyage --dimension 1024 --prewarm --repetitions 3
```

`--voyage` autoriza enviar los textos y consultas del dataset al proveedor.
Usar únicamente fuentes públicas o datos expresamente autorizados: no expedientes,
identidades de víctimas ni conversaciones reales. `--prewarm` agrupa llamadas
REST normales, **no utiliza Batch API**. Esta última no recibe tokens gratuitos.

## Qué se compara


| Estrategia  | Implementación y límite                                                                               |
| ------------- | --------------------------------------------------------------------------------------------------------- |
| `flat_bm25` | Control léxico sin filtros temporales, solo harness.**No es LightRAG**.                                |
| `bm25`      | BM25 sobre subchunks elegibles a la fecha solicitada.                                                   |
| `metadata`  | BM25 de contenido + norma/componente, fusionado por RRF.                                                |
| `hybrid`    | Lo anterior + coseno `voyage-context-4`, RRF y `rerank-3-lite` cuando hay proveedor.                     |
| `ppr`       | Añade PPR personalizado sobre membresías CTV elegibles. No reproduce el modelo completo Three-Tier.   |
| `tree`      | Añade ranking extractivo norma → subchunk. No implementa la construcción HAT/merge/collapse de Ψ-RAG. |

Sin proveedor, `hybrid`, `ppr` y `tree` son ablaciones **offline** sin embeddings
ni rerank. La API declara `dense_status=not_run`; no atribuirles calidad Voyage.
No hay generación LLM, traducción ni evaluación de respuestas en este harness.

### Relación con los papers locales


| PDF en`docs`                                              | Concepto tomado, no afirmación de reproducción                                                                                                    |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `2505.00039 SAT-Graph.pdf`                                | Work/CTV/CLV/Action, selección temporal determinística y cadena causal. Núcleo previo + nueva búsqueda/historial; no toda la OpenAPI del paper. |
| `A_New_Metadata_Aware_Retrieval_Augmented_Generation.pdf` | Subchunks con metadatos heredados y recuperación híbrida. No se relajan fecha/jurisdicción/norma ni autorización.                               |
| `FAIA-430-FAIA260735.pdf`                                 | PPR y fusión de rankings. Sin navegación LLM ni grafo semántico de doble nivel completo.                                                         |
| `zhao26bk.pdf`                                            | Recuperación multigranular extractiva. Sin agente de abstracción ni consolidación HAT completa.                                                  |

Los PDFs son las versiones descargadas del repositorio, no una garantía de que
sean las últimas versiones publicadas. La metodología de lanzamiento sigue en
[SAT-GRAPH-EVALUATION-PLAN.md](SAT-GRAPH-EVALUATION-PLAN.md).

## Fronteras de seguridad jurídica

1. Se aceptan únicamente CTV revisadas, alcance PE, idioma español, intervalo
   semiabierto `[valid_from, valid_to)` y fecha dentro de `checked_through`.
2. Dos versiones concurrentes del mismo Work causan abstención para ese Work;
   el score semántico no resuelve conflictos normativos. El filtro explícito de
   norma/componente tampoco se relaja.
3. Subchunks sin overlap conservan rangos Unicode globales y hash del texto.
   **Son ventanas de caracteres**, no un parser estructural jurídico terminado.
4. Cada grupo contextual reúne los chunks ordenados de **una sola CTV**. No se
   mezclan leyes ni versiones históricas en su contexto. Una CTV demasiado grande
   se rechaza: no se parte/trunca silenciosamente.
5. El contexto selecciona como máximo un subchunk por CTV. Esto evita inflar las
   métricas, pero todavía puede omitir evidencia distribuida en artículos largos.

## Coste, caché y límites


| Control                        | Valor / semántica                                                                                                                                                    |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Modelos                        | `voyage-context-4` + `rerank-3-lite`; dimensión por defecto 1024.                                                                                                    |
| Límite observado de la cuenta | Tier 0: 3 RPM / 10K TPM para ambos modelos, verificado en dashboard el 10/10/2026 hora Perú. No se añadió método de pago.                                         |
| Configuración de ritmo        | `VOYAGE_REQUESTS_PER_MINUTE=3`, `VOYAGE_TOKEN_BOUND_PER_MINUTE=9000` (margen conservador).                                                                            |
| Cuota diaria local             | 100 intentos / 100.000 unidades de reserva por defecto; no es presupuesto monetario ni saldo de tokens gratuitos.                                                     |
| Reserva                        | Bytes UTF-8 + margen.**No es el tokenizer Voyage ni uso facturado**. Respuestas válidas aportan `usage.total_tokens` por separado.                                   |
| Pacing                         | Ventana persistente de 61 segundos por huella de clave/modelo. Respeta RPM y reserva TPM. No coordina claves diferentes de la misma organización ni clientes ajenos. |
| Reintentos                     | Uno por defecto, solo 429 explícito, respetando`Retry-After` y espera acotada. Nunca timeout/401/500 ambiguos. Intentos fallidos conservan reserva.                  |
| Caché contextual              | Hash de modelo/dimensión/input_type/todos los chunks ordenados de la CTV. Cambiar un grupo no invalida los demás.                                                   |
| Caché rerank                  | Hash de consulta/documentos canónicos/modelo/parámetros. Aun con caché, el resultado se somete al selector temporal antes de construir contexto.                   |
| Persistencia compartida        | CLI y endpoint usan`backend/docs/voyage_cache.sqlite3`, ignorado en Git. Otros archivos/clientes no comparten esta cuota.                                             |

La caché guarda vectores/índices/scores, no la clave ni el texto devuelto por la
API. Los embeddings siguen siendo datos derivados potencialmente sensibles:
proteger este archivo, no compartirlo ni tratarlo como anonimizado.

Precios de lista consultados: contexto 4 USD 0,12/M tokens y rerank 3 lite
USD 0,02/M tokens; verificar [precios](https://docs.voyageai.com/docs/pricing),
[límites](https://docs.voyageai.com/docs/rate-limits) y saldo real antes de escalar.
En rerank, la consulta se cuenta una vez por documento candidato; reducir
candidatos reduce coste, `top_k` por sí solo no reduce el texto procesado.
Esto no demuestra por qué Cohere cobró S/50: falta reconciliar su factura y las
llamadas de extracción/generación/ingesta del camino legado.

## Leer los informes sin sobreinterpretarlos

### Evidencia local de ingeniería (10/10/2026)


| Ejecución                                                                            | Resultado comprobado                                                                                                                                                                                       |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Smoke real                                                                            | context-4: 2 chunks de 256 dimensiones; rerank: 2 documentos. 41 tokens reportados.                                                                                                                        |
| Primer benchmark real                                                                 | HTTP 429, sin informe final; motivó pacing y checkpoints. No se cuenta como éxito.                                                                                                                       |
| `temp/sat-experiments/voyage-1024-v2.json`                                            | Completado: 12 casos development × 6 estrategias × 3 repeticiones. 10 solicitudes / 607 tokens reportados: 155 de preparación contextual y 452 rerank.                                                  |
| `temp/sat-experiments/voyage-1024-v3-cached.json`                                     | Replay con nDCG@k corregido y cero solicitudes nuevas; no es una segunda validación independiente del modelo.                                                                                             |
| `voyage-256-v3.json`, `voyage-512-v3.json`, `voyage-2048-v3.json` en la misma carpeta | Las tres dimensiones adicionales completaron la misma ablación: 2 llamadas / 155 tokens de preparación cada una; rerank reutilizado. Ledger compartido acumulado: 16 intentos / 1.072 tokens reportados. |

El control plano encuentra 9/10 CTV gold, devuelve evidencia inelegible en 11/12
preguntas y no cumple ninguna de las cuatro abstenciones. SAT BM25 y variantes
encuentran 10/10 y cumplen 4/4 abstenciones en este fixture construido para probar
esos mecanismos. BM25 ya resuelve todo el recall: no hay prueba de ganancia de
Voyage en recall ni de superioridad PPR/tree. El nDCG del replay es 0,98997 para
BM25/metadatos y 1 para variantes con Voyage, diferencia demasiado pequeña y
sintética para decidir el modelo jurídico.

Las cuatro dimensiones alcanzan el mismo techo de este fixture. **Se mantiene
1024 como default**, no se declara ganadora a 256 por ahorrar almacenamiento.
Voyage y Cohere son espacios vectoriales diferentes aunque ambos tengan 1024
dimensiones: no se reutiliza el índice Cohere para Voyage ni se mezclan vectores.
El dashboard mostró USD 0,00 y créditos gratuitos disponibles para ambos modelos;
sus contadores agregados observados no coinciden con el ledger local. No se ha
reconciliado definitivamente el uso/factura ni se promete coste cero futuro.

La primera pasada híbrida tuvo esperas por tier 0 (p95 agregado ≈15,6 s);
PPR/tree reutilizaron cache y no son controles equivalentes de latencia. No
extrapolar estos tiempos a producción. La suma de tokens de este run tampoco
es la factura total: el smoke y el intento anterior usaron otros ledgers locales.

Smoke runtime tras reinicio: backend/frontend HTTP 200 y SonarQube `UP`.
Las rutas admin contestaron 404 según la protección existente cuando admin está
deshabilitado/sin clave; no se habilitaron ni se debilitó esa protección para
demostrar el experimento. Sus contratos autorizados se prueban con cliente HTTP
de integración offline. El CLI es el camino usado para el benchmark real.

Verificación de código: **419 tests Python, 23 Node y 95 frontend aprobados**;
3 evaluaciones LLM reales omitidas y 2 xfail temporales heredados. 50 casos
focalizados nuevos pasan; Black sobre 10 archivos nuevos y `git diff --check`
sin errores. El scanner Sonar falló antes del análisis por
`AccessDeniedException` en `backend/.pytest_cache`, un caché local inaccesible.
**Quality Gate no evaluado**; no se borró el caché ni se cambiaron permisos para
sortearlo. Que el servidor esté UP no significa que el análisis haya pasado.

- El JSON final declara `completed` o `incomplete`, hashes de dataset/snapshot,
  split, dimensión, entorno y política de caché. El archivo `.progress.jsonl`
  se vacía tras cada caso; una interrupción conserva ese progreso, no un éxito.
- Los fallos Voyage no se puntúan como abstenciones ni como calidad cero. Se
  registran aparte; las métricas parciales incluyen casos previstos/fallidos.
- Se reportan recall/precisión micro y macro, nDCG@k, abstenciones, elegibilidad,
  ranking estable, p50/p95 y bootstrap pareado. La unidad de gold es CTV, **no
  cobertura exacta de todos los pasajes**. n/a permanece n/a.
- El bootstrap trata preguntas como unidades; el fixture diminuto y correlacionado
  no permite inferencias estadísticas sobre desempeño jurídico. Las repeticiones
  calientes no son muestras nuevas de calidad.
- La preparación tiene coste/latencia propios. Primera pasada puede mezclar
  caché y red; no etiquetarla "cold". El ledger incluye otros runs del día que
  compartieron archivo; los contadores por run separan preparación/consultas.
- El split `heldout` solo se usa con `--split heldout`; estos dos casos inventados
  no constituyen un conjunto jurídico ciego. Falta partición real por familia y
  linaje temporal revisada por abogados.

## API administrativa

`POST /sat-graph/search` recibe un `SearchPlan` con `query` y `as_of=YYYY-MM-DD`.
Por defecto no sale a red. `?use_voyage=true` requiere opt-in y configuración local.
`GET /sat-graph/history?resource_id=...&component=...` expone historial causal,
no una afirmación de aplicabilidad al caso concreto. Ambas rutas requieren la
API key administrativa y que los endpoints admin estén habilitados.
`/query` y `/stream` siguen utilizando el camino previo; no cambiaron a Voyage.

## Unidades de revisión y rollback


| Unidad           | Revisar / revertir de forma conjunta                                                                                             |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Selector SAT     | `backend/retrieval/sat.py` + `test_sat_retrieval.py`: filtros, offsets, matemáticas, historial.                                 |
| Proveedor opt-in | `backend/retrieval/voyage.py` + `test_voyage_provider.py`: contrato REST, caché, cuotas, 429, secretos.                         |
| API              | Imports/rutas nuevas en`backend/main.py`, settings Voyage y `test_sat_search.py`. No revertir cambios SAT de ingesta anteriores. |
| Investigación   | `backend/research/`, fixture y `test_sat_benchmark.py`: reproducibilidad y fallos explícitos.                                   |

No se han creado commits ni cambiado las ramas. El checkout tenía cambios previos.
Rollback operativo: no activar `use_voyage` y volver a `metadata`; no borrar bases
SAT/legadas ni caches para "arreglar" resultados. Respaldar SQLite consistentemente
antes de una migración; exportar informes antes de limpiar artefactos locales.

## Ensayo documental con PDF oficiales (11/10/2026)

Se congelaron **12 unidades/11 Works de tres PDF**, 16 preguntas development
(13 con referencia y 3 negativas) y 6 heldout reservadas. Los originales, URLs,
hashes, páginas y correcciones se describen en
[la revisión de corpus](SAT-GRAPH-CORPUS-REVIEW.md). Las fuentes son:

- [Congreso: Ley 30364 original](https://www3.congreso.gob.pe/Docs/DGP/DIDP/files/ley_30364.pdf),
  PDF, p. 1–2, artículos 1–9; artículo 10 parcial excluido. Publicación 23/11/2015.
- [Contraloría: copia del Código Penal](https://apps.contraloria.gob.pe/UNETEALCONTROL/pdf/07_635.pdf),
  PDF, p. 67–68, artículos 149/150 seleccionados visualmente; cobertura temporal desconocida.
- [El Peruano: DL 1323 original](https://busquedas.elperuano.pe/dispositivo/NL/1471010-2),
  PDF, p. 4 / impresa 10: reemplazo **citado** de Ley 30364 art. 8, no artículo 8 host de
  DL 1323. Publicación 06/01/2017; otras normas parciales del archivo excluidas.

El adaptador `research/documentary.py` crea `DocumentaryVersion`, **no CTV**.
Valida bytes PDF, hashes, exportación Docling, selección de spans y referencias.
Una URL declarada del catálogo oficial no es firma del editor; hashes prueban
integridad, no fidelidad OCR. La revisión visual IA se declara como tal.
El plan selecciona ediciones/source_ids y no acepta fecha de vigencia `as_of`.
La recuperación pública SAT sigue rechazando estos nodos documentales.

### Resultados comprobados

Tres repeticiones por caso; cobertura = contención del fragmento gold completo
en el contexto retornado, no evaluación de respuesta/entailment jurídico.


| Development                                        | Recall unidades macro | Cobertura referencias macro |  nDCG@k | Abstenciones correctas |
| ---------------------------------------------------- | ----------------------: | ----------------------------: | --------: | -----------------------: |
| flat BM25 sin filtros                              |                  100% |                      73.08% | 0.87019 |                    0/3 |
| BM25 documental, ventana fija                      |                  100% |                      80.77% |       1 |                    2/3 |
| Voyage 1024+rerank, hybrid/PPR/tree, `candidates=4`    |                  100% |                      80.77% |       1 |                    2/3 |
| BM25 documental, segmentación natural, **sin API** |                  100% |                    **100%** | 0.97161 |                    2/3 |

Los tres fallos de cobertura fija recuperaban el artículo correcto, pero la cita
cruzaba una frontera de 1000 caracteres (`documentary-window-diagnostics-v1.json`).
Un único subchunk por versión no podía contenerla, aunque el rerank mejorara.
La política `chunk_policy=paragraph` prioriza párrafos/líneas/oraciones/espacios,
con fallback acotado, sin overlap ni normalización. Es opt-in experimental: no
cambia el chunker SAT público. **nDCG development baja ligeramente**, por lo que
no todos los indicadores mejoran. No se eligieron nuevos textos/referencias.

Tras congelar esa política se ejecutaron las seis preguntas heldout ya existentes,
sin retocarlas: BM25 fijo y natural conservan 5/5 unidades y 100% referencias, nDCG 1 y
1/1 abstención. PPR offline queda 80% referencias en ambos; tree 100%. Heldout no muestra
ganancia adicional ni regresión BM25 en esta muestra diminuta. Fue diseñado por
el mismo agente y **no sellado por un tercero**; no es validación jurídica ciega.

### Coste observado y artefactos

Todos los archivos siguientes están en `temp/corpus-review`; salidas exclusivas
y checkpoints append-only. `implementation-documentary-v1/` conserva los cuatro
módulos exactos previos a la ablación natural y su manifiesto SHA256.


| Archivo                                                                                | Resultado                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `documentary-offline-v1.json`                                                          | Ventanas fijas, seis rankers, cero API.                                                                                                                                   |
| `documentary-voyage-1024-v1.json`                                                      | **incomplete/exit 1**: 20 candidatos excedían la cota local 9000 TPM antes de enviar rerank. Prewarm 3 llamadas/3806 tokens reportados. No se puntúan fallos como abstención. |
| `documentary-voyage-1024-v2-budget4.json`                                              | **completed/exit 0**, mismos PDF/gold, `candidates=20` → 4/`top_k=3` por presupuesto. Prewarm 26 cachehits/0 llamadas; rerank 17 llamadas/14565 tokens: 14 hybrid, 2 PPR, 1 tree.             |
| `documentary-offline-v3-paragraph.json`                                                | Solo cambia la segmentación respecto a v2; mejora documental sin nuevas llamadas.                                                                                        |
| `documentary-offline-v1-heldout.json`, `documentary-offline-v3-paragraph-heldout.json` | Contraste offline posterior al congelamiento, sin ajuste adicional.                                                                                                       |

Nuevo consumo de estos runs: **20 solicitudes/18371 tokens reportados**, sumando
prewarm v1 y rerank v2. Ledger diario compartido 36/19443 incluye 16/1072 anteriores;
no es factura ni uso total de cuenta. Reserva conservadora 93830/100000: quedan
6170 unidades locales, **no** 6170 tokens gratuitos. No subir límites ni lanzar otra
ingesta de pago sin revisar presupuesto/dashboard. Las repeticiones calientes
y el cache compartido impiden comparar latencias como si todas fueran cold.

**Recomendación experimental:** priorizar segmentación fiel y cache, limitar
candidatos antes del rerank y exigir ganancia medida antes de usarlo en todas
las consultas. Aquí Voyage no superó BM25 en las métricas documentales principales.
No cambiar a un embedding más caro para compensar frases partidas. No explica
por sí solo la factura S/50 del chat legado: falta su desglose real.

### Reproducir sin API

Desde la raíz, con los artefactos exactos del bundle y un nombre de salida nuevo:

```powershell
.venv/Scripts/python.exe -X utf8 backend/research/sat_benchmark.py `
  temp/corpus-review/documentary-dataset-v3-paragraph.json `
  --output temp/corpus-review/replay-paragraph.json --repetitions 3
```

Añadir `--split heldout` selecciona esa partición. `--voyage --prewarm` implica
envío externo y cuota; no ejecutarlo por defecto ni usar expedientes privados.

### Límites y verificación

- El snapshot no tiene `contains_version`: PPR no prueba propagación por un
  grafo de membresías. Tree es parcial. No hay Actions/intervalos normativos.
- Falla la abstención semántica ante un trámite de visitas no soportado; los
  filtros duros sí excluyen edición/artículo faltantes. No basta subir recall.
- No hay baseline LightRAG real, generación/citas de respuestas ni gold experto.
- **59 pruebas focalizadas; 506 Python aprobadas, 3 skipped opt-in, 2 xfail previos,
  20 warnings**. Black/diffcheck sin errores. Ningún reinicio backend ni migración.
- Se conserva el rollback del adaptador/harness/tests; no borrar evidencia ni
  revertir las correcciones independientes top-k/exit-status.

## Próximo criterio de avance

El parser candidato y la revisión documental ya existen. Falta completar
fuentes/fechas/acciones antes de promover CTV,
probar múltiples subchunks por unidad y abstención por falta de soporte.
Después: gold legal independiente, baseline LightRAG limpio, ablaciones de
dimensión/candidatos/presupuesto y verificación de respuestas/citas.
Sin ello **no puede elegirse honestamente el "mejor" modelo para uso jurídico**.

## Ablación independiente de etapas — 11/10/2026

**Resultado:** separar embeddings/rerank no revela una mejora de cobertura
respecto a BM25 en esta muestra. Sí cambia algunos rankings y mejora las
variantes estructurales débiles. No justifica rerank obligatorio en cada consulta.
Se reutilizaron resultados ya pagados/calculados: **cero llamadas nuevas**.

Mismo `documentary-dataset-v2-budget4.json`: ventanas **fijas**, tres PDF oficiales,
16 casos development, 13 respondibles/14 unidades gold, 3 negativos, 3 repeticiones.
No usa NotebookLM, Markdown legado, vectores ni grafo previos del chat.


| Variante completa                 | Unidades recuperadas | Cobertura refs macro |   nDCG@k | Abstenciones |
| ----------------------------------- | ---------------------: | ---------------------: | ---------: | -------------: |
| BM25 documental                   |                14/14 |               80.77% |        1 |          2/3 |
| Hybrid léxico, sin ambos modelos |                14/14 |               80.77% |        1 |          2/3 |
| Hybrid + dense, sin rerank        |                14/14 |               80.77% |        1 |          2/3 |
| Hybrid + dense + rerank           |                14/14 |               80.77% |        1 |          2/3 |
| PPR sin membresías, solo léxico |                14/14 |               80.77% | 0.904758 |          2/3 |
| PPR sin membresías + dense       |                14/14 |               80.77% | 0.971610 |          2/3 |
| PPR sin membresías + ambos       |                14/14 |               80.77% |        1 |          2/3 |
| Tree léxico                      |                13/14 |               76.92% | 0.970242 |          2/3 |
| Tree + dense                      |                14/14 |               80.77% | 0.993825 |          2/3 |
| Tree + ambos                      |                14/14 |               80.77% |        1 |          2/3 |

La precisión macro no vacía de hybrid mejora ligeramente de 0.392857 a 0.404762
al añadir dense (39 → 38 resultados), sin mejora adicional por rerank. No hay
prueba estadística de superioridad ni gold experto. El combinado reproduce
**exactamente** los rankings del run Voyage v2 anterior; el default se conserva.
No confundir el techo de recall de unidades con fidelidad de contexto ni
con calidad de respuestas. La mejora de referencias mediante segmentación
natural descrita arriba fue **otro** ensayo, sin API.

### Resultado incompleto, no ganador

`rerank_only` cambia candidatos al retirar dense. Su caché tiene resultados
para 10/16 casos hybrid, 6/16 PPR y 10/16 tree; faltan 22 pares estrategia/caso.
El proceso devuelve 1 y estado `incomplete`. No se imputan fallos como abstención
ni cero calidad, y sus macros de submuestra **no son comparables** con la tabla
completa. No se hicieron llamadas para rellenar esos huecos.

### Implementación y reproducción segura

`RankStages` controla dense/rerank por separado, con booleanos estrictos y
default combinado. `api_stages` y `stage_executions` distinguen etapas realmente
ejecutadas de flags solicitados; `api` mantiene el total. BM25/metadata no llaman
modelos; prewarm solo corre si dense está habilitado. Un error real de proveedor
mantiene el circuit breaker; un miss de caché afecta solo al caso/lote ausente.

`--cache-only` abre SQLite con `mode=ro`, sin clave, lectura de `.env`, red,
inicialización de esquema ni reserva de cuota. Requiere una base compatible ya
existente. Miss explícito: `VoyageCacheMiss`; no es falta de evidencia jurídica.
Es mutuamente excluyente con `--voyage`, que sí permite gasto externo.

```powershell
.venv/Scripts/python.exe -X utf8 backend/research/sat_benchmark.py `
  temp/corpus-review/documentary-dataset-v2-budget4.json `
  --output temp/corpus-review/replay-dense-only.json `
  --cache-only --stages dense_only --prewarm --repetitions 3
```

`--stages`: `lexical`, `dense_only`, `rerank_only`, `combined`. Sin proveedor,
ningún modelo se ejecuta aunque los flags estén solicitados. La caché debe
coincidir en texto/grupo/orden/modelo/dimensión/tipo; no reutiliza embeddings
de ventanas fijas para párrafos distintos.

### Evidencia, presupuesto y rollback

En `temp/corpus-review/`:

- `documentary-stages-v4-{lexical,dense_only,combined}.json`: completed/exit 0.
- `documentary-stages-v4-rerank_only.json`: incomplete/exit 1, 22 misses.
- Cada informe tiene log y checkpoint append-only `.progress.jsonl`.
- `documentary-stages-v4-verification.json`: hashes dataset/implementación/caché
  y ledger antes/después. **Bytes de caché y ledger idénticos**: 36 solicitudes,
  reserva 93830 y 19443 tokens reportados. Son datos locales diarios, no factura.
- `implementation-documentary-v4/`: copia de los cuatro módulos exactos del
  experimento, verificada contra los hashes del manifiesto antes de otra edición.

**Pruebas focalizadas:** 133 aprobadas (proveedor, retriever, harness, adaptador
documental y catálogo de tests). Suite Python completa: **539 aprobadas,
3 skipped opt-in, 2 xfail previos, 20 warnings**. Black 7 archivos y diffcheck pasan.
Backend 8000/frontend 3000 responden 200; Sonar 9000 está UP 26.9.0.129388. Esto no
prueba Quality Gate (scanner previo falló por permisos). Sin reiniciar backend
ni migrar el chat; pruebas del código nuevo por CLI, no del proceso ya iniciado.

**Rollback de esta unidad:** retirar flags/guards `RankStages` y estadísticas
por etapa de `retrieval/sat.py`, passthrough de `research/documentary.py`, modo
`cache_only`/`VoyageCacheMiss` de `retrieval/voyage.py`, selección de etapas/misses
por caso de `research/sat_benchmark.py` y sus tests/catalogación. Conservar el
retriever, proveedor, bundle, caché, resultados y correcciones top-k/exit-status
anteriores. No revertir módulos completos ni borrar datos del usuario.

Al cerrar v4 faltaban membresías verificables: PPR todavía no tenía aristas
`contains_version`. La siguiente sección registra esa incorporación y su contraste.

## Membresías oficiales reales y PPR controlado — v5

**Decisión experimental:** conservar BM25 como control principal; **no activar
PPR por defecto**. El grafo ya propaga, pero empeora desarrollo frente al mismo
corpus con las aristas deshabilitadas. Ningún resultado implica vigencia jurídica.

### Corpus y correcciones trazables

La revisión visual IA usa los mismos PDF oficiales, sin NotebookLM ni nuevas
descargas: Ley 30364 p. 1–2 y DL 1323 p. 4 para las membresías; CP 149/150 permanece como
artículos raíz seleccionados, sin promover su parser en cuarentena. Son
**45 versiones documentales**: 12 artículos/33 hijos; 131 nodos/168 aristas,
incluyendo 33 `contains_version`. No hay CTV aprobados ni nuevas fechas normativas.


| Ámbito                                                     | Relaciones revisadas |
| ------------------------------------------------------------- | ---------------------: |
| Ley 30364 art. 2 → numerales 1–6                                 |                    6 |
| Ley 30364 art. 3 → numerales 1–6                                 |                    6 |
| Ley 30364 art. 5 → incisos a–c; art. 7 → a–b                      |                    5 |
| Ley 30364 art. 8 → a–d; inciso d → numerales 1–4                 |                    8 |
| Reemplazo **citado** de art. 8 en DL 1323 → a–d; inciso d → 1–4 |                    8 |

Docling también añadió números 2/4/7 a continuaciones sin marcador del art. 3.
En una nueva copia se reclasifican `#/texts/26`, 28, 31 y 60 como TextItem, sin
cambiar texto, geometría ni proveniencia. Frente al Markdown corregido v1 se
eliminan únicamente esos nueve caracteres generados. Los PDF, Docling original,
bundle v1 y datasets previos permanecen intactos. El builder actual reproduce
**exactamente** el snapshot congelado v1: defaults nuevos no cambian su hash.

`parent_component`/`kind` exigen misma edición PDF/recurso, contención estricta,
páginas compatibles, ruta y taxonomía coherentes, y hermanos disjuntos. No se
hereda autoridad de un parser automático ni se adivina parentado por indentación.
Los numerales 1–4 de violencia económica pertenecen al inciso d, no directamente
al artículo. Son selecciones documentales revisadas, no una regla universal para
todos los formatos jurídicos.

### Diseño causal y métricas

Plan congelado antes de resultados: **seis development + tres heldout**, todas
con tres repeticiones, `--stages lexical`, `candidates=4`/`top_k=3` y sin proveedor.
Controles raíz fixed/paragraph, y corpus con hijos fixed/paragraph × membresías
verified/disabled. Entre graph on/off cambian **solo** ese flag; nodos, snapshot,
gold, referencias y preguntas son idénticos. Los rankers no PPR conservan
exactamente sus rankings, como comprobación del aislamiento de la ablación.

`evaluation_level=documentary_root` se solicita explícitamente: recall/precision/
nDCG deduplican artículos raíz dentro de la misma edición. `runs` conserva IDs
granulares y `evaluation_runs` su correspondencia; `hit_spans` y `context_bytes`
permiten auditar evidencia/presupuesto. Para cobertura, un hijo solo acredita
una referencia si su intervalo **real retornado** la contiene íntegramente.
Pertenecer al artículo correcto no basta. Modo `version` anterior sigue default.


| Development, corpus con hijos | Gold raíz recuperado | Referencias macro |   nDCG@k |
| ------------------------------- | ----------------------: | ------------------: | ---------: |
| BM25 fixed                    |                 14/14 |              100% |        1 |
| BM25 paragraph                |                 14/14 |              100% | 0.971610 |
| PPR fixed, sin aristas        |                 14/14 |              100% | 0.943220 |
| PPR fixed, con aristas        |                 13/14 |            92.31% | 0.894687 |
| PPR paragraph, sin aristas    |                 14/14 |              100% | 0.886440 |
| PPR paragraph, con aristas    |                 12/14 |            84.62% | 0.846154 |

Los controles solo raíz BM25 siguen 80.77% fixed/100% paragraph. Añadir unidades
menores permite cubrir frases completas aun con fixed; no demuestra que las
aristas sean responsables de esa mejora. Tampoco comparar cambios de desempate
entre v4/v5 como efecto causal del grafo: la corrección cambia offsets/IDs.

PPR expande a versiones no semilla en 14/16 casos development. En paragraph con
aristas desplaza el art. 1 de `purpose` y el art. 6 de `family-trust`; el control sin
aristas sí los recupera. `ppr_runs` registra aristas elegibles/utilizadas, semillas,
versiones puntuadas y expandidas. Filtros de edición/componente se aplican antes
de propagación y nunca se relajan. El control sin aristas todavía tiene sesgo de
personalización; no es sinónimo de BM25 puro.

Heldout paragraph: BM25 y PPR on/off recuperan 5/5 gold y 100% referencias; PPR nDCG
sube 0.9 → 0.926186, aún por debajo de BM25 (nDCG = 1). Es el heldout pequeño ya existente,
diseñado por el mismo agente, no validación externa. Todos los controles duros
se abstienen; el negativo semántico de visitas sigue fallando (development 2/3).
No se ajustaron pesos/semillas usando esos resultados ni se eligió ganador legal.

### Reproducir y verificar

```powershell
.venv/Scripts/python.exe -X utf8 backend/research/sat_benchmark.py `
  temp/corpus-review/documentary-dataset-v5-memberships-paragraph-verified.json `
  --output temp/corpus-review/replay-memberships.json --stages lexical --repetitions 3
```

Usar el dataset `...-disabled.json` deshabilita solo las aristas; `--split heldout`
selecciona esa partición. No añadir `--voyage`: la caché anterior no cubre todos
los nuevos grupos contextuales, y quedan pocas unidades de reserva local.
Offsets distintos por sí solos no invalidan un vector si texto/grupo son idénticos.
Una inspección `cache_only` de Voyage 1024 confirmó 11/45 grupos documentales cacheados
en fixed y 8/45 en paragraph; las 14 consultas development elegibles sí están cacheadas.
Faltan 34/37 grupos, respectivamente. Esa inspección no genera vectores ni gasta cuota;
no es una evaluación de ranking dense. Evidencia: `...-cache-coverage.json`.

Artefactos en `temp/corpus-review/`:

- `documentary-bundle-v5-{roots,memberships}.json`, seis datasets v5 y nuevas
  copias `ley-30364-structure-corrected-v5.*`; script de congelamiento reproducible.
- `documentary-memberships-v5-*-{development,heldout}.json`: nueve completed/exit 0,
  con logs/checkpoints exclusivos. `...-run-plan.json` conserva el plan previo.
- `...-verification.json`: hashes inputs/módulos, fuentes/caché/ledger idénticos
  antes/después: 36 solicitudes/93830 reserva/19443 tokens reportados; **0 llamadas nuevas**.
- `...-diagnostics.json`: contraste de rankings, spans/contexto duplicados y
  estadísticas PPR. `implementation-documentary-v5/`: cuatro módulos exactos.

En paragraph development, el contexto BM25 suma 25839 bytes UTF-8, de los cuales
3641 se repiten por solapamiento artículo/hijo (9/16 consultas). PPR on suma 26200,
con 4732 duplicados (11/16). Son bytes del contexto retornado, **no** tokens Voyage
ni una factura. El diagnóstico une intervalos solo dentro del mismo PDF/Markdown;
no fusiona ediciones diferentes. Este desperdicio motiva el próximo ajuste.

**Verificación:** 150 focalizadas; **556 Python aprobadas, 3 skipped opt-in, 2 xfail
previos, 20 warnings**. Black/diffcheck pasan. Sin reiniciar/migrar chat ni tocar la
base canónica. PPR/tree siguen adaptaciones parciales, no reproducciones de los
papers completos ni sistemas validados para decisiones legales.

**Rollback de esta unidad:** retirar parent/kind/validación/root-map del adaptador,
`membership_policy`, control/diagnósticos PPR y evaluación por raíz/spans del harness,
con sus tests/catalogación. Conservar stage/cache-only, referencias/version scoring
anteriores, evidencia y snapshots congelados. No revertir módulos completos.

**Próximo trabajo:** reducir contexto solapado artículo/hijo y permitir fragmentos
complementarios sin duplicar crédito; después abstención por soporte. Medir una
política de propagación con anclaje léxico antes de considerar PPR operativo.

### Revisión exploratoria: ponderar la mezcla con PPR

La estrategia `ppr` de v5 **ya era mixta**: fusiona con RRF los rankings de BM25
de texto, BM25 con metadatos y PPR, cada uno con peso 1. Con un proveedor y las
etapas habilitadas puede añadir embeddings y reranking; el ensayo de membresías
anterior fue exclusivamente léxico, sin esas dos etapas. Sus resultados no son
una comparación de BM25 frente a PPR puro.

Para revisar el aporte del grafo se probaron, offline, pesos PPR de 0, 0.25, 0.5
y 1, manteniendo los pesos de texto y metadatos en 1 y el parámetro RRF en 60.
Peso 0 es una mezcla de texto y metadatos **sin contribución PPR**, no BM25 puro.
Se usaron los dos datasets v5 de 16 preguntas de desarrollo, tres repeticiones,
`top_k=3`, cuatro candidatos y las mismas referencias documentales IA.

| Segmentación | Variante | Unidades esperadas recuperadas | Cobertura de referencias | nDCG |
|---|---|---:|---:|---:|
| Fija | BM25 solo | 14/14 | 100 % | 1.000000 |
| Fija | Mezcla, PPR 0.25 | 14/14 | 100 % | 0.971610 |
| Fija | Mezcla, PPR 0.5 | 14/14 | 100 % | 0.971610 |
| Fija | Mezcla, PPR 1 | 13/14 | 92.31 % | 0.894687 |
| Párrafos | BM25 solo | 14/14 | 100 % | 0.971610 |
| Párrafos | Mezcla, PPR 0.25 | 14/14 | 100 % | 0.971610 |
| Párrafos | Mezcla, PPR 0.5 | 13/14 | 92.31 % | 0.923077 |
| Párrafos | Mezcla, PPR 1 | 12/14 | 84.62 % | 0.846154 |

Todas las variantes se abstuvieron correctamente en 2 de 3 negativos. El peso 1
reprodujo exactamente los rankings originales; peso 0 coincidió con la estrategia
de metadatos. Peso 0.25 cambió cuatro rankings granulares respecto a BM25 en cada
segmentación, sin cambiar la cobertura de referencias, pero tampoco demostró una
mejora en estas métricas. El nDCG fijo fue menor que con BM25 solo.

Es un **análisis exploratorio posterior** a observar v5, no una selección validada:
no se probó un nuevo conjunto independiente ni calidad de respuestas. El heldout
anterior ya fue observado. No hubo embeddings, reranking ni llamadas externas; no
se cambiaron el retriever ni el chat. PPR 0.25 es un candidato para una evaluación
posterior, no un nuevo default. Persisten el contexto duplicado y la abstención
semántica insuficiente.

Evidencia y reproducción local: `temp/corpus-review/explore_mixed_ppr_20261026.py`
y `temp/corpus-review/mixed-ppr-weights-exploratory-20261026.json`; el informe
incluye hashes de datasets, código y script, métricas y resultados por caso.
El script no sobrescribe un informe existente y modifica la fusión únicamente en
memoria durante el experimento. Reversión: retirar esta sección y esos dos
artefactos experimentales; no es necesario revertir código operativo ni corpus.

### Configurar la mezcla sin editar código

El benchmark admite `--ppr-weight` entre 0 y 2. El valor predeterminado 1
conserva la fusión anterior; 0 no aporta candidatos ni puntuación desde PPR.
Los pesos del texto y los metadatos siguen en 1. La opción solo afecta la
estrategia PPR, no modifica BM25 ni activa el chat SAT. El peso y las etapas
solicitadas quedan registrados en el informe y su checkpoint.

```powershell
.venv/Scripts/python.exe -X utf8 backend/research/sat_benchmark.py `
  temp/corpus-review/documentary-dataset-v5-memberships-paragraph-verified.json `
  --output temp/corpus-review/mixto-ppr-025-nuevo.json `
  --stages lexical --ppr-weight 0.25 --repetitions 3
```

Elegir un nombre de salida nuevo para cada variante. `--stages lexical` no usa
embeddings; las demás etapas requieren un proveedor o `--cache-only`. `--voyage`
es una opción explícita de red que puede consumir cuota y enviar texto externo.
El peso 0,25 es exploratorio, no un valor validado ni el predeterminado.
