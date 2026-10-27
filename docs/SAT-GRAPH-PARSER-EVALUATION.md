# Reutilizar Docling; acotar la adaptación jurídica peruana

**Evaluación del 2026-10-10.** No es necesario construir un conversor PDF/OCR
ni un estándar jurídico propio. Recomendación: reutilizar Docling para extracción
y conservar solo un adaptador PE para candidatos, citas, offsets y validaciones
SAT. El prototipo determinista añadido es experimental: no certifica vigencia ni
es un parser universal de legislación. Las pruebas pequeñas siguientes no eligen
un ganador sobre el corpus real.

## Opciones y encaje

| Opción | Qué reutilizamos | Límite para este proyecto | Decisión provisional |
|---|---|---|---|
| Docling, ya instalado | PDF, OCR, orden de lectura, tablas, JSON/proveniencia y jerarquía de encabezados | Un encabezado detectado no identifica por sí solo instrumento, artículo host o texto citado de reforma | Base de extracción; conservar JSON, no solo Markdown |
| Bluebell + Cobalt | Marcado jurídico explícito → XML Akoma Ntoso; lectura/validación XML | Bluebell requiere su sintaxis/indentación; no convierte por sí solo PDF español crudo en artículos | Útil para edición asistida/interoperabilidad, no reemplazo directo del autodetector |
| Indigo | Gestión editorial, consolidación y publicación legislativa | Es una aplicación Django completa y un cambio de plataforma, no una pequeña librería para el backend actual | Evaluar si se necesita un equipo de edición de legislación, no incorporarlo por defecto |
| Unstructured | Particionado PDF en elementos, estrategias OCR/layout | Elementos de documento no equivalen a identidades y versiones jurídicas revisadas | Candidato comparador de extracción si Docling falla en PDFs concretos |
| Fuente oficial ya estructurada | Importar jerarquía explícita, evitando reconstrucción desde PDF | Debe comprobarse que existe ese formato para cada recurso y registrar la fuente; HTML visual puede seguir siendo plano | Preferible cuando esté disponible; el store actual de SourceEvidence sigue siendo PDF/Markdown |

Fuentes primarias consultadas:
- [DoclingDocument](https://github.com/docling-project/docling/blob/main/docs/concepts/docling_document.md): representación estructurada y procedencia.
- [Jerarquía nativa Docling](https://github.com/docling-project/docling/blob/main/docs/usage/heading_levels.md): inferencia por bookmarks, numeración y estilo; deshabilitada por defecto.
- [Bluebell](https://laws.africa/bluebell/) y [gramática](https://laws.africa/bluebell/grammar/): marcado explícito con jerarquía, citas y listas.
- [Cobalt](https://github.com/laws-africa/cobalt): biblioteca para trabajar con AKN.
- [Akoma Ntoso / OASIS](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part1-vocabulary.html): vocabulario XML, no motor que infiere corrección jurídica desde un PDF.
- [Indigo](https://github.com/laws-africa/indigo): plataforma editorial basada en Django/Cobalt/Bluebell.
- [Unstructured](https://docs.unstructured.io/open-source/core-functionality/partitioning): particionado por tipos y estrategias.

No se verificó un parser mantenido que cubra automáticamente todo el derecho
peruano. Eso **no demuestra que no exista**. Slaw tiene gramáticas por tradición
jurídica y requiere adaptaciones; Indigo documenta su sustitución por Bluebell,
por lo que no sería la primera opción para desarrollo nuevo.
([Slaw](https://github.com/laws-africa/slaw), [migración Indigo](https://indigo.readthedocs.io/en/latest/changelog.html)).

## Pruebas ejecutadas, no solo comparación de descripciones

### Bluebell 5.0.0

Entorno aislado `temp/parser-eval-venv`, Cobalt 9.0.1, sin modificar dependencias
ni lockfiles del backend. Un ejemplo ficticio con un capítulo y dos artículos:

| Entrada | Capítulos XML | Artículos XML |
|---|---:|---:|
| Español crudo: CAPÍTULO / Artículo | 0 | 0 |
| Marcado explícito: CHAPTER / ARTICLE con indentación | 1 | 2 |

El texto crudo se conservó como párrafos. XML válido no prueba que se hayan
reconocido las unidades jurídicas correctas. El experimento muestra la necesidad
de preparación de entrada en este ejemplo, no una tasa de error general.
Bluebell declara LGPLv3+; revisar obligaciones y distribución antes de incorporarlo.
([Paquete oficial y licencia](https://pypi.org/project/bluebell-akn/)).

### Jerarquía nativa de Docling 2.133.0

Seis encabezados ya clasificados como tales en un DoclingDocument, sin PDF,
OCR, bookmarks ni estilo. Secuencia: título, capítulo, artículo, artículo,
capítulo, artículo.

| Entrada para inferencia | Niveles resultantes |
|---|---|
| Encabezados españoles | 1, 1, 1, 1, 1, 1 |
| Equivalentes ingleses | 1, 2, 3, 3, 2, 3 |
| Copia candidata con tres alias españoles → marcadores ingleses | 1, 2, 3, 3, 2, 3 |

El original quedó intacto. **Inferencia:** es viable reutilizar el motor con una
adaptación pequeña de etiquetas en una vista candidata. No demuestra que todos
los artículos de un PDF sean detectados como encabezados ni resuelve reformas.
Nunca reexportar esa copia como evidencia original: cambiarían texto y hashes.

Artefactos reproducibles locales, ignorados por Git:
`temp/{bluebell_probe.py,docling_heading_probe.py}` y
`temp/parser-evaluation/{bluebell-probe.json,docling-probe.json}`.

### Smoke sobre un PDF público real

Se descargó un PDF del [repositorio MIMP](https://repositorio.mimp.gob.pe/bitstreams/65c5e60a-4098-4aad-97b1-eb284bc801fc/download),
SHA-256 `d227f054e2ff01e73834697dd872d128bf553e430c4fa014eef3d6426c314f84`.
Convertidas únicamente **páginas 3–4 de 76**, sin OCR ni reconocimiento de tablas:
40,02 s de una ejecución, 9.668 caracteres, seis candidatos de artículo;
52 items alineados de forma única, 3 ambiguos y 6 no alineables exactamente.
No es un benchmark de latencia ni de vigencia; no se ha revisado el documento completo.

La inspección visual de ambas páginas confirmó un límite importante: el decreto
aprobatorio y el TUO tienen secuencias de artículos separadas. El prototipo detectó
las seis fronteras, pero **no separó correctamente el TUO como segundo instrumento**.
Además, Docling fusionó en Markdown texto de cierre y del título siguiente, y no
clasificó como heading uno de los artículos. Esto impide sustituir todas las reglas
por niveles de encabezado o declarar correcta la estructura por su conteo.
Conservar layout, revisión y límites de instrumentos es necesario; no corregirlo
con una regex apresurada ni marcar ese AST como aprobado.

La descarga directa desde Congreso respondió 403; se usó otra fuente oficial sin
eludir la restricción. La conversión MIMP escribió todos los artefactos y el reporte;
el wrapper PowerShell terminó con código 1 por un warning en stderr de Hugging Face,
sin traceback de conversión. El smoke CLI de almacenamiento se verifica por separado.
CLI `stage` y `structure` sobre esos archivos reales, en una base temporal: ambos
**exit 0**, JSON Docling idéntico al exportado, 19 nodos AST, `review_required=true`,
documento `pending_review` y **0 CTV revisadas**. No se publicó en la base del corpus.
Artefactos: `temp/parser-evaluation/official-smoke-report.json`, PNG de páginas 3/4
y `official-pages-1-2.*` (nombre histórico; **el rango real es 3–4**, no 1–2).

## Qué código propio sigue justificándose

1. Adaptación de marcadores PE: artículo único, disposiciones, incisos y separación
   de instrumentos. No reinventar OCR, detección de tablas ni XML.
2. Conservar rangos exactos y hashes; texto original separado de vistas normalizadas.
3. Marcar ambigüedades: artículos citados en una reforma, encabezados repetidos,
   tablas y alineaciones no únicas. No atribuirles identidad jurídica automáticamente.
4. Promoción SAT solo con manifiesto revisado, fechas y causalidad explícitas.

Un LLM podría proponer estructura para casos inciertos, pero no debería ser la
primera pasada de todos los documentos ni aprobar su propia salida. Añade coste,
egreso de datos y otra superficie de error. Los embeddings tampoco sustituyen
el parser: sirven para recuperación semántica después de definir unidades.

## Implementación candidata actual

- `backend/ingestion/legal_structure.py`: reglas contextuales PE, AST con rangos
  anidados y `segments` sin overlap que reconstruyen el Markdown completo.
- `conversion.py` / `docling_processor.py`: una conversión produce Markdown y JSON;
  adaptadores antiguos pueden devolver solo Markdown con diagnóstico de layout ausente.
- `sat_graph/store.py`: SourceEvidence sin cambios; nuevos CandidateParse y
  CandidateComponent, tabla aditiva `sat_parses`, sin Work/CTV/CLV/Action nuevos.
  Si hay varios parses del mismo PDF, se exige `parse_id`; nunca se escoge el último.
- Alineación Docling únicamente exacta y única en ambos lados. `prov.charspan`
  se conserva en espacio local del item, nunca como offset Markdown global.
  JSON de tablas/elementos no alineables permanece disponible, sin geometría inventada.

El AST todavía se obtiene de reglas candidatas propias; el adaptador de alias
del motor Docling **solo está probado experimentalmente**, no sustituye aún ese
AST en producción. Es importante no confundir viabilidad con integración terminada.

### Revisar candidatos

Desde `backend`, con el entorno existente y rutas explícitas:

```powershell
uv run --no-sync python -m ingestion.sat_graph stage --pdf "D:\corpus\ley.pdf" --markdown "D:\corpus\ley.md" --docling-json "D:\corpus\ley.docling.json"
uv run --no-sync python -m ingestion.sat_graph --output "D:\corpus\estructura.json" structure --evidence-id EVIDENCE_ID --parse-id PARSE_ID
```

El JSON debe corresponder al mismo documento convertido. Los hashes prueban
inmutabilidad, **no** que alguien no haya suministrado un layout ajeno. Comparar
con el PDF antes de aprobar. Sin `--docling-json` se registra layout ausente.
La API equivalente es `GET /sat-graph/structure?evidence_id=...&parse_id=...`,
protegida por la configuración administrativa existente; no habilitarla para demos.

## Evaluación siguiente y criterio de decisión

Comparar sobre los **mismos PDFs y anotaciones humanas**, no ejemplos distintos:

- corpus pequeño de normas, reformas con texto citado, TUO, escaneados, compendios
  multi-instrumento y tablas; separar desarrollo de evaluación retenida;
- precisión/recall de fronteras y etiquetas, exactitud de padres, cobertura sin
  pérdida/duplicación, alineación de página y citas host frente a payload;
- minutos de corrección humana por documento, latencia p50/p95, RAM y coste real;
- downstream: mismo recuperador Voyage, mismas consultas y gold jurídico revisado.

Comparadores: Docling sin adaptación, Docling + alias, adaptador PE actual y
Bluebell con marcado **contabilizando trabajo humano de preparación**. Añadir
Unstructured solo si hay fallos reales de extracción; no multiplicar dependencias
por catálogo. No llamar a ninguna alternativa ganadora por superar fixtures.

## Unidad de trabajo, verificación y reversión

Sin commits/PR nuevos. Parser/persistencia/CLI/HTTP/conversión y sus tests forman
una unidad separable de los experimentos de retrieval. Revertir **solo** sus
imports, llamadas y endpoints nuevos, los módulos nuevos y las adiciones de
store/CLI/tests; preservar la ingesta SAT y las revisiones previas. La tabla
aditiva y los nodos candidatos pueden quedar en SQLite: las rutas de recuperación
autoritativa ignoran tipos candidatos. No borrar fuentes ni hacer down-migration
destructiva. Restaurar backup consistente si se decide retirar datos.

Verificación focalizada: **81 aprobados** (parser, SAT, upload/batch, evidencia y
catálogo de tests). Harness CLI/HTTP real con conversores simulados: mismos
artefactos, autenticación, ambigüedad y ausencia de llamadas LLM. No certifica OCR,
runtime ya arrancado ni calidad jurídica. La inferencia Docling y Bluebell sí se
ejecutaron con las bibliotecas reales en probes aislados.

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest -q tests/backend/unit/test_legal_structure.py tests/backend/unit/test_sat_graph.py tests/backend/integration/test_sat_ingestion.py tests/backend/unit/test_source_evidence.py tests/scripts/unit/test_repository_layout.py
.venv\Scripts\python.exe -X utf8 -m pytest -q
git diff --check
```

Suite Python completa tras los cambios: **444 aprobados**, 3 evaluaciones reales
omitidas opt-in, 2 xfail anteriores y 20 warnings. No se ejecutaron nuevamente
frontend/E2E ni scanner Sonar; no extrapolar este resultado a un Quality Gate.
