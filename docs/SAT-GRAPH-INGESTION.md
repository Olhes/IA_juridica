# Ingesta SAT-Graph para el piloto jurídico peruano

**Resultado:** carga PDF y lote publican evidencia y candidatos en un grafo SAT
SQLite separado, sin llamadas LLM/embedding por defecto. El catálogo inicial
contiene **28 recursos oficiales** para violencia y alimentos. Catalogar un enlace
**no** significa haber ingerido su texto ni certificar su vigencia.

## Estado real y límites


| Disponible                                                                          | Todavía no disponible / no garantizado                                                                        |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Source, CandidateText, Resource y Topic persistentes                                | Descarga automática de todos los recursos y comprobación de autenticidad oficial                             |
| Work, CTV, CLV y Action mediante manifiestos revisados                              | Corpus de normas peruanas aprobado por abogados: aún cero versiones revisadas al sembrar el catálogo         |
| Selección determinística por componente, fecha y cobertura                        | Búsqueda semántica de componentes en SAT y migración del chat a recuperación SAT                           |
| Jerarquía Work y membresía de versiones explícitas; reutilizar hijos sin cambios | Propagación automática de reformas, restitución, excepciones, retroactividad o vigencia controvertida       |
| Hash PDF/Markdown, segmentos exactos, URL y revisión en aristas                    | Correspondencia página PDF ↔ Markdown y preservación de tablas complejas certificadas                       |
| Transacción SQLite, idempotencia/reinicio, validación de intervalos               | Equivalencia jurídica castellano/quechua, firma digital del revisor o cumplimiento íntegro de la OpenAPI SAT |

Es una **implementación local inicial** del modelo estructural/temporal/causal,
no una certificación jurídica ni un reemplazo listo para producción. La
[API SAT de referencia](https://github.com/hmartim/sat-graph-api) distingue
descubrimiento probabilístico de operaciones determinísticas; su alcance no
incluye una implementación de ingesta. Work/CTV/CLV se corresponden con
Item/Version/TextUnit de esa API. Véase también el
[artículo original](https://arxiv.org/abs/2505.00039).

## Recursos que usar primero

Los enlaces y prioridades completos están en
`D:\Web\IA_juridica\backend\ingestion\sat_graph\peru_resources.json`.
La investigación del catálogo se realizó el 7 de octubre de 2026; no es una
garantía de cobertura exhaustiva de reformas hasta esa fecha.


| Tema / prioridad | Fuente oficial                                                                                                                                                                                                                                                                                                                    | Qué incorporar al grafo tras revisión                                                                                                                                                                                                                                            |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Violencia / P1   | [Ley 30364 original](https://www3.congreso.gob.pe/Docs/DGP/DIDP/files/ley_30364.pdf) y [TUO DS 004-2020-MIMP](https://elperuano.pe/normaselperuano/2020/09/06/1882613-1/1882613-1.htm)                                                                                                                                            | Definiciones, tipos, sujetos protegidos, denuncia y medidas de protección. Mapear numeración original/TUO; el TUO no es otra ley independiente.                                                                                                                                  |
| Violencia / P1   | [Reglamento DS 009-2016-MIMP](https://www.gob.pe/institucion/mimp/normas-legales/20809-009-2016-mimp)                                                                                                                                                                                                                             | Recepción, riesgo, competencias, procedimientos y coordinación; verificar cada versión por artículo.                                                                                                                                                                           |
| Violencia / P1   | [DS 005-2022-MIMP](https://www3.congreso.gob.pe/Docs/DGP/DIDP/files/ds_005-2022-mimp.pdf), [DS 002-2025-MIMP](https://www.gob.pe/institucion/mimp/normas-legales/6661714-002-2025-mimp), [DS 004-2025-MIMP](https://www.gob.pe/institucion/mimp/normas-legales/6850857-004-2025-mimp)                                             | Cambios del reglamento; Action → termina CTV anterior / produce CTV nueva. No inferir fechas efectivas de fechas del portal.                                                                                                                                                      |
| Ambos / P1       | [DL 1703](https://www.congreso.gob.pe/Docs/DGP/DIDP/files/decret_legislativo_1703.pdf)                                                                                                                                                                                                                                            | Cambio institucional de Defensa Pública y disposición que modifica el Reglamento 30364.                                                                                                                                                                                          |
| Violencia / P1   | [Seguimiento del Congreso](https://www3.congreso.gob.pe/didp/procedimientos-parlamentarios/leyes-reglamentadas-2015)                                                                                                                                                                                                              | Localizar otras reformas: 016-2021, 006-2023, 009-2023, entre otras. Es directorio, no texto normativo. Completar también cambios de la propia Ley 30364 (p. ej., DL 1386 y leyes modificatorias).                                                                                |
| Ambos / P1       | [Código Penal, copia Congreso](https://www2.congreso.gob.pe/sicr/cendocbib/con5_uibd.nsf/C835D25C36641543052586F2001DA486/%24FILE/CODIGOPENAL.pdf)                                                                                                                                                                               | Art. 149 para omisión de prestación de alimentos; localizar versiones actuales de 122-B, 108-B y reglas pertinentes para violencia. Esta copia histórica no basta para fijar vigencia actual.                                                                                   |
| Alimentos / P1   | [Código Civil DL 295](https://www.leyes.congreso.gob.pe/Documentos/DecretosLegislativos/00295.pdf)                                                                                                                                                                                                                               | Arts. 472, 474, 481, 482, 483 y 487: alcance, obligados, cuantía y modificaciones. Promulgación original no equivale a consolidación actual.                                                                                                                                    |
| Ambos / P1       | [Ley 27337](https://www.gob.pe/institucion/congreso-de-la-republica/normas-legales/3366849-27337) y [edición MIMP 2026](https://www.gob.pe/institucion/mimp/informes-publicaciones/7858302-codigo-de-los-ninos-y-adolescentes)                                                                                                   | Interés superior del niño, alimentos (92–97) y proceso; la fecha editorial 2026 no es la vigencia de todos los artículos.                                                                                                                                                      |
| Alimentos / P1   | [Código Procesal Civil DL 768 / TUO](https://www.leyes.congreso.gob.pe/Documentos/DecretosLegislativos/00768.pdf), [Ley 28439](https://www.mimp.gob.pe/files/direcciones/dgfc/diff/normatividad_alimentos/1_Ley_28439.pdf), [Ley 31464](https://leyes.congreso.gob.pe/Documentos/2021_2026/ADLP/Texto_Consolidado/31464-TXM.pdf) | Demanda, resolución, liquidación y ejecución; verificar textos de 566-A y 568. Distinguir proceso de alimentos de persecución penal; no sugerir que cualquier impago produce condena automática.                                                                              |
| Alimentos / P1   | [Ley 28970](https://leyes.congreso.gob.pe/Documentos/Leyes/28970.pdf), [DL 1377](https://leyes.congreso.gob.pe/Documentos/2016_2021/Decretos/Legislativos/2018/DL137720180818.PDF), [DS 008-2019-JUS](https://busquedas.elperuano.pe/dispositivo/NL/1737747-1)                                                                    | REDAM y cambios causales; completar texto de Ley 31928 usando [referencia del Congreso](https://comunicaciones.congreso.gob.pe/despacho-informa/promulgan-ley-que-promueve-inscripcion-de-parte-en-registro-de-deudores-alimentarios-morosos/), que es una noticia y NO una norma. |
| Violencia / P1   | [RM 100-2021-MIMP: protocolo CEM](https://www.gob.pe/institucion/mimp/normas-legales/1780515-100-2021-mimp)                                                                                                                                                                                                                       | Atención y derivación. La RM deja sin efecto la guía RM 157-2016-MIMP; revisar cambios posteriores antes de usar como actual.                                                                                                                                                   |
| Violencia / P2   | [Ley 30490](https://www.gob.pe/institucion/congreso-de-la-republica/normas-legales/3601024-30490) y [DS 024-2021-MIMP](https://www.gob.pe/institucion/mimp/normas-legales/2040707-024-2021-mimp)                                                                                                                                  | Protección de personas adultas mayores y medidas específicas.                                                                                                                                                                                                                    |
| Violencia / P2   | [CONADIS: Ley 29973 y reglamento](https://www.gob.pe/institucion/conadis/informes-publicaciones/223512-ley-general-de-la-persona-con-discapacidad-y-su-reglamento)                                                                                                                                                                | Accesibilidad y ajustes razonables; verificar normativa base y cambios, no promover el directorio como ley.                                                                                                                                                                        |
| Servicios / P1   | [Línea 100](https://www.gob.pe/44181-solicitar-ayuda-en-casos-de-violencia-contra-las-mujeres-e-integrantes-del-grupo-familiar-linea-100), [directorio WARMI ÑAN](https://www.gob.pe/institucion/warmi%C3%B1an/informes-publicaciones/3487068-directorio-de-servicios-del-programa-nacional-warmi-nan)                          | CEM y Familia, SAU, SAR, Chat 100 y derivación. Datos operativos separados de CTV legales; revalidar contactos antes de recomendar. Nunca publicar ubicación de refugios confidenciales.                                                                                         |
| Servicios / P1   | [ALEGRA](https://www.gob.pe/562-obtener-asesoria-legal-gratis-en-los-centros-de-asistencia-legal-gratuita-alegra), [directorio](https://www.gob.pe/institucion/minjus/informes-publicaciones/3300912-directorio-de-centros-de-asistencia-legal-gratuita-alegra)                                                                   | Asistencia/derivación y requisitos, contrastando cambios institucionales de 2026.                                                                                                                                                                                                 |

**No importar indiscriminadamente:** expedientes privados, nombres/DNI de víctimas,
direcciones protegidas, noticias como si fueran leyes, proyectos/anteproyectos como
derecho vigente ni recopilaciones sin fecha de corte. Jurisprudencia del PJ/TC
puede añadirse en una segunda fase, con órgano, expediente, fecha y alcance de
precedente revisados; el catálogo actual no incorpora una selección jurisprudencial.

**Hallazgo de desactualización:** el [directorio MIMP de alimentos](https://www.gob.pe/institucion/mimp/informes-publicaciones/5478027-normatividad-nacional-en-materia-de-alimentos)
enlaza el reglamento REDAM DS 002-2007-JUS. El
[DS 008-2019-JUS](https://busquedas.elperuano.pe/dispositivo/NL/1737747-1)
lo deroga. Incluso un directorio oficial necesita revisión temporal.

## Flujo implementado

```text
PDF → conversión local Docling → Markdown exacto → SourceEvidence inmutable
    → transacción SAT: Source + CandidateText → pending_review
    → revisor valida publicación, artículo, vigencia y cambios
    → manifiesto → transacción SAT: Work + CTV + CLV + Action + auditoría
    → resolver por componente y fecha → disposición citada o abstención
```

- Upload y batch usan `stage_document`; reintentos idénticos conservan IDs.
- Los candidatos son rangos de caracteres Unicode sobre el Markdown exacto,
  con hash de texto. No se cortan artículos por `MAX_CHUNK_SIZE=1000`, ni se
  duplican por overlap. OCR, columnas y encabezados requieren revisión humana.
- CTV usa `[valid_from, valid_to)`. `valid_to=null` NO permite extrapolar más allá
  de `checked_through`, la fecha hasta la que el revisor comprobó cobertura.
- El ID Work usa recurso/componente, no nombre del archivo; el CTV conserva ID
  cuando una Action revisada lo termina. CLV identifica idioma y texto exacto.
- Una reforma requiere versiones anterior/nueva del mismo Work y un fragmento
  causal verificado. Cierres, versiones, aristas y manifiesto se confirman juntos.
- Solapamientos, ciclos, referencias inexistentes, hashes/rangos erróneos y
  membresías temporales inconsistentes rechazan TODA la revisión.
- La jerarquía se declara explícitamente y en orden padres antes de hijos.
  `memberships` relaciona CTV padre/hijo; un hijo sin cambios puede reutilizarse.
  Cerrar un hijo exige cerrar/reversionar sus padres afectados: no se propaga
  automáticamente ni se valida solo la arista nueva.
- Una revisión fallida deja el documento pendiente y lanza error; una transacción
  SAT fallida no se informa como `committed`. No hay outbox remoto porque el único
  destino SAT es la misma SQLite. Un futuro destino Neo4j necesita outbox/reconciliación.
- Después de publicar evidencia, los fallos de upload conservan PDF/Markdown para
  recuperación. El lote conserva Markdown y mueve el PDF a `failed`; restaurar
  y reintentar no sobrescribe evidencias divergentes.

## Uso local sin APIs de pago

Ejecutar desde **`D:\Web\IA_juridica\backend`**, utilizando el entorno uv del proyecto.
No se necesita Cohere/OpenAI para estos comandos.

```powershell
# Sembrar solo enlaces/temas; no descarga PDFs ni aprueba vigencia.
uv run --no-sync python -m ingestion.sat_graph catalog

# Un PDF oficial ya descargado y su Markdown ya convertido, rutas explícitas.
uv run --no-sync python -m ingestion.sat_graph stage --pdf "D:\corpus\ley.pdf" --markdown "D:\corpus\ley.md"

# Sustituir EVIDENCE_ID por el ID devuelto; se escribe UTF-8 sin sobrescribir.
uv run --no-sync python -m ingestion.sat_graph --output "D:\corpus\revision.json" draft --evidence-id EVIDENCE_ID --resource-id pe:ley:30364

# SOLO después de revisión humana y completar el borrador.
uv run --no-sync python -m ingestion.sat_graph review "D:\corpus\revision.json"

uv run --no-sync python -m ingestion.sat_graph --output "D:\corpus\grafo.json" export
```

`--db` permite seleccionar otra base SQLite antes del subcomando. Por defecto:
`D:\Web\IA_juridica\backend\docs\sat_graph.sqlite3`. Los artefactos locales no
se versionan en Git. Los tests usan directorios temporales, no esta base real.

### Completar un manifiesto

El borrador mantiene `null` en identidad de componente, revisión y fechas:
**no se puede promover sin completarlo**. Revisar:

1. `source_resource_id`: publicación causal del PDF; `units[].resource_id`:
   instrumento afectado. Un TUO/reforma puede dar texto de la misma Ley 30364.
2. `component` estable, `label` y `parent_component`, si existe. No confiar en
   detección regex para adjudicar artículos repetidos en disposiciones modificatorias.
3. `start/end/text_sha256`: contrastar el fragmento convertido con el PDF oficial;
   corregir OCR antes de publicar evidencia, no sobrescribir una conversión registrada.
4. `valid_from/valid_to`, `checked_through` y `effective_date_basis`: explicar la
   regla/disposición de vigencia verificada. Ni upload ni fecha editorial son vigencia.
5. `reviewer/reviewed_at`: responsable real y fecha/hora con zona. El campo es
   trazabilidad declarativa, no autenticación del abogado ni firma digital.
6. `actions`: `action_key`, `kind=enact|amend|repeal`, `effective_on`, segmento causal,
   `terminates/produces` con IDs CTV exactos. `version_id(ReviewedUnit)` permite
   calcular los IDs nuevos antes de aprobar; los anteriores salen de `export`.
7. `memberships`: `parent_version/child_version` explícitos, cuando se registra
   estructura histórica. No se copian todos los capítulos/artículos en cada reforma.

Solo se admiten textos normativos revisados en castellano y alcance PE en esta
primera versión. Una guía/directorio/servicio no puede promoverse a Work/CTV.
No editar SQLite directamente. Una corrección de norma ya aprobada o ampliación
de cobertura necesita una futura operación de corrección/revalidación auditada;
actualmente el store rechaza cambios divergentes de la misma identidad.

## API administrativa y compatibilidad

- `GET /knowledge-graph?engine=sat`: recursos, candidatos, Work/CTV/CLV/Action,
  aristas con evidencia y estado por documento. Requiere admin habilitado + `X-API-Key`.
- `GET /sat-graph/resolve?resource_id=pe:ley:30364&component=art-1&as_of=2026-10-07`:
  resolución exacta o `abstain`; **no** busca texto libre ni invoca LLM.
- Sin `engine=sat`, `/knowledge-graph` conserva el grafo LightRAG por compatibilidad.
  El visualizador/chat existente aún no consume el grafo SAT.
- `SAT_INGESTION_LEGACY_RAG=false` es el default. `true` habilita escritura adicional
  LightRAG para comparar, con costes de extracción/embeddings; no vuelve sus relaciones
  autoritativas. `RAG_ENGINE=lightrag` continúa describiendo la consulta heredada.
- La respuesta de ingesta distingue `sat_graph.write_state=committed` de
  `sat_graph.review_state=pending_review`; éxito de almacenamiento no implica éxito jurídico.
- Un documento marcado `reviewed` tiene al menos un manifiesto aprobado, no
  necesariamente todos sus artículos revisados. Solo las CTV/CLV explícitamente
  aprobadas participan en `resolve`; el resto sigue siendo candidato no autoritativo.

## Tokens, rollout y reversión

Esta ruta SAT no llama LLM ni embeddings en ingesta; la revisión y el almacenamiento
son locales. No elimina coste de OCR/CPU, ni coste del chat legado. No se ha medido
un ahorro mensual ni atribuido la factura previa de S/50 a un componente concreto.

Próxima fase: corpus reducido revisado → benchmark abogado → recuperación SAT en
sombra → búsqueda de Work/artículos (léxica primero; embeddings solo de textos nuevos
y deduplicados si se necesitan) → rerank opcional → una respuesta LLM con presupuesto
acotado y citas SAT. No generar entidades/reformas con LLM durante el lote por defecto.
No activar respuestas jurídicas SAT en producción solo porque pasaron tests sintéticos.

Los datos LightRAG existentes no se borran ni se importan como SAT. Para reversión de
la escritura de ingesta puede activarse la flag explícita; para revertir una revisión
SAT, restaurar backup consistente de SQLite, no borrar nodos sueltos. Conservar PDF,
Markdown y manifiestos. No usar el importador GraphML destructivo para esta base.

## Verificación y unidades de revisión

Desde `D:\Web\IA_juridica`:

```powershell
uv run --no-sync python -m pytest -q tests/backend/unit/test_sat_graph.py tests/backend/integration/test_sat_ingestion.py
uv run --no-sync python -m pytest -q
```

Los casos están explicados en `D:\Web\IA_juridica\tests\README.md`.
Verificación realizada: **369 tests Python aprobados**, 3 omitidos de modelos
reales y 2 xfail anteriores de la recuperación temporal heredada. Smoke local
de CLI: 28 recursos / 0 versiones jurídicas revisadas. No hubo llamadas LLM
de pago, ni evaluación jurídica, OCR real o prueba de interfaz de usuario.
Suite SAT focalizada: **41 casos aprobados**, cobertura combinada de líneas/ramas
del paquete SAT **92%** (store **95%**); no es cobertura global del proyecto.
Unidades separables para revisión (sin crear commits ni PR automáticamente):

1. Contratos/store y catálogo: identidad, tiempo, causalidad y pruebas offline.
2. Integración upload/batch/API: confirmaciones, compatibilidad y recuperación.
3. Guías/corpus: verificación jurídica y siguiente fase de lanzamiento.

## Estructura jurídica candidata y reutilización de parsers

Upload y batch conservan ahora JSON Docling junto al AST candidato, cuando el
conversor ofrece ese artefacto. No cambia SourceEvidence ni la aprobación SAT.
Los candidatos estructurales se consultan con CLI `structure` o la ruta admin
`GET /sat-graph/structure`; múltiples parses requieren `parse_id` explícito.
El borrador `draft` conserva su contrato anterior y no autopromueve el AST.

[Evaluación de alternativas y verificación](SAT-GRAPH-PARSER-EVALUATION.md):
Docling como base existente, Bluebell/Cobalt para marcado AKN e interoperabilidad,
adaptación PE acotada. La jerarquía nativa con alias solo está en pruebas; el AST
actual sigue siendo un prototipo de reglas candidatas, no un parser universal.
