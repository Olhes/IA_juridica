# Reconstruir el corpus SAT únicamente desde PDF oficiales

**Decisión del usuario, 11 de octubre de 2026:** no utilizar resúmenes NotebookLM.
La nueva ingesta y los experimentos solo usarán PDF oficiales verificados. Un
Markdown derivado de Docling es una transcripción de trabajo, no otra fuente.

La revisión realizada aquí es **documental por IA**: procedencia, fidelidad de
extracción, estructura y citas. No se presenta como aprobación por abogado ni
como certificación de vigencia a 2026. Los experimentos anteriores de doce
preguntas siguen siendo sintéticos; estos PDF no los convierten retroactivamente
en un benchmark jurídico.

## Estado del corpus heredado

Inventario de solo lectura al comenzar esta revisión:

| Ubicación | Estado observado | Decisión para el corpus nuevo |
|---|---|---|
| `backend/docs/processed` | 18 Markdown, incluidos resúmenes generados y publicaciones secundarias | No utilizar como fuente ni recuperar sus embeddings/grafo heredados |
| `backend/docs/raw_pdfs` | Ningún PDF, solo `.gitkeep` | No hay original verificable para esos Markdown en esta carpeta |
| `backend/docs/sat_graph.sqlite3` | 28 Resource, 2 Topic, 0 documentos y 0 CTV | El catálogo no es contenido jurídico aprobado |

No se borran los archivos ni se certifica que todos sean falsos. Su exclusión es
de **la nueva ingesta/evaluación**. No se ha depurado ni migrado el chat Cohere/
LightRAG existente; no confundir esta selección con una limpieza de producción.

## PDF oficiales adquiridos para revisión

| Fuente pública | Identidad de bytes | Alcance de la revisión inicial |
|---|---|---|
| [Congreso: publicación original de Ley 30364](https://www3.congreso.gob.pe/Docs/DGP/DIDP/files/ley_30364.pdf) | SHA256 `7ee605f76b4ba65d0b792e9b82aadcce4baec629260955ad953a47a169851125`; 12 páginas | Edición original de 2015, no consolidación vigente; inspección visual p. 2 y conversión piloto p. 1–2 |
| [MIMP: compilación TUO y Reglamento](https://repositorio.mimp.gob.pe/bitstreams/65c5e60a-4098-4aad-97b1-eb284bc801fc/download) | SHA256 `d227f054e2ff01e73834697dd872d128bf553e430c4fa014eef3d6426c314f84`; 76 páginas | Revisión visual y estructural p. 3–4; readquisición HTTP 200 con bytes idénticos |
| [Contraloría: copia del Código Penal](https://apps.contraloria.gob.pe/UNETEALCONTROL/pdf/07_635.pdf) | SHA256 `12e8b91f3221ce7945d8c4095fcdafde8ff4d00fff964b4d0b0e199a9f5a2f6f`; 247 páginas | Inspección visual del artículo 149 en p. 67 y conversión piloto p. 67–68; cobertura temporal desconocida |

Los artefactos locales están en `temp/corpus-review`. No se distribuyen estos
PDF en Git ni se presume una licencia de redistribución por estar publicados.
Que un PDF esté en un dominio estatal no demuestra que sea una consolidación
actualizada ni que todas sus anotaciones sean parte del texto normativo.

### Fuentes no seleccionadas

- La descarga del Código Penal desde la URL ensayada del Congreso respondió 403.
  No se evadió la restricción; se buscó una copia pública en otra entidad oficial.
- La copia SENAMHI de 468 páginas está guardada como evidencia de descarte, pero
  no integra el corpus seleccionado: extracción con caracteres U+FFFD, referencias
  rotas y artículos repetidos entre secciones/ediciones. No se “repararon” letras
  inventando el texto. La copia Contraloría tiene cero U+FFFD en extracción nativa.
- No se usan LP, Juris, NotebookLM ni documentos sin un original PDF oficial
  verificable. Tampoco índices, proyectos de ley o noticias como norma promulgada.

## Corrección real: separar decreto y TUO sin editar evidencia

En el PDF MIMP, el DS 004-2020 termina con las firmas en p. 3 y el TUO comienza en
p. 4. Docling fusionó la última firma con el título del TUO en una línea Markdown.
La misma denominación también aparece en el preámbulo: separar todas sus
coincidencias mediante una expresión regular sería incorrecto.

Se añadió un **sidecar de revisión documental** con offset exacto, hash del
Markdown, hash del encabezado, autor IA, fecha con zona y fundamento. El parser
divide únicamente su vista; no modifica los bytes del PDF/Markdown ni “corrige”
su contenido. Resultados del caso real:

| Control | Antes | Después |
|---|---:|---:|
| Instrumentos candidatos | 1 | 2 |
| Nodos estructurales | 19 | 20 |
| Artículos conservados | 1,2,3,1,2,3 | 1,2,3,1,2,3 |
| CTV aprobados | 0 | 0 |

Original y corrección coexisten en `official-candidates.sqlite3`, con parse_id
distintos y estado `pending_review`. La corrección documental **no** construye
un `ReviewManifest`, añade vigencia ni transforma candidatos en autoridad.

### Reproducir con el CLI

```powershell
# Desde la raíz; sustituir rutas por los PDF/derivados exactos de la adquisición.
$env:PYTHONPATH = "backend"
.venv/Scripts/python.exe -m ingestion.sat_graph `
  --db temp/corpus-review/replay.sqlite3 stage `
  --pdf temp/parser-evaluation/mimp-reglamento-30364-unverified.pdf `
  --markdown temp/parser-evaluation/official-pages-1-2.md `
  --docling-json temp/parser-evaluation/official-pages-1-2.docling.json `
  --documentary-review temp/corpus-review/tuo-documentary-review.json
```

El nombre histórico `official-pages-1-2` corresponde a **páginas PDF 3–4**, no 1–2.
El sidecar nuevo se rechaza si cambia el Markdown, si el rango/hash es incorrecto
o repetido, o si intenta convertir una cita/código en instrumento. No decide
automáticamente qué parse prevalece: cuando hay varios se exige `parse_id`.

## Verificación y siguiente paso

- 36 pruebas focalizadas de parser/correcciones aprobadas, incluidas 13 nuevas.
- 74 pruebas de núcleo SAT, recuperación, benchmark y HTTP aprobadas.
- Caso MIMP real: partición completa, hash fuente intacto, parses coexistentes,
  separación corregida y cero promociones jurídicas.
- Suite Python completa: **457 aprobadas, 3 omitidas opt-in, 2 xfail previos**;
  20 warnings. Esto no es una evaluación de calidad jurídica ni llamadas API.

### Resultado de conversión del piloto

| Vista Docling | Resultado observado | Uso permitido ahora |
|---|---|---|
| Ley 30364, p. 1–2 | SUCCESS, 12244 caracteres, cero U+FFFD; 10 artículos candidatos | Revisión documental; artículo 10 incompleto excluido |
| Código Penal, p. 67–68 | SUCCESS, 4262 caracteres, cero U+FFFD; cero artículos AST | Cuarentena estructural, no evaluación de recuperación |

El Código Penal muestra por qué `SUCCESS` no prueba fidelidad estructural: el
rango empieza dentro de una reforma citada, queda una comilla sin contexto y
Docling fusiona los artículos 149/150 en un párrafo. El parser conserva la evidencia
y no atraviesa la región protegida para inventar artículos. Hace falta ampliar
contexto y revisar límites; no se desactivó la protección de citas para elevar
artificialmente la cobertura.

La primera conversión de doce páginas terminó con exit 1 sin informe y sin proceso
Python vivo. El intento acotado, con importación Torch previa y logs mediante
subprocess, terminó con exit 0. No está demostrada la causa del primer fallo.

Se congelaron `official-source-manifest.json` y `official-candidate-graph.json`:
**3 Source, 144 nodos, 233 aristas y 0 CTV aprobados**, en una base experimental
aislada. Incluye el artefacto en cuarentena para trazabilidad, **no** como evidencia
recuperable. `legal_benchmark_ready=false`.

Las vistas parciales permanecen fuera de la base SAT del backend. El almacén
canónico exige una única conversión Markdown por PDF: registrar una vista parcial
allí impediría reemplazarla silenciosamente por una conversión completa. Cada
revisión experimental debe conservar su snapshot y sus rangos de páginas.

**Pendiente:** revisar la integridad de las conversiones nuevas, completar las
modificatorias y fechas por disposición, y preparar preguntas/citas de referencia
documentales claramente etiquetadas como IA. Los artículos incompletos en los
extremos de una selección de páginas no se usarán como evidencia completa.

El primer piloto no aportaba un resultado de recuperación. La continuación ya
preparó un [benchmark documental de PDF oficiales](SAT-GRAPH-EXPERIMENTS.md#ensayo-documental-con-pdf-oficiales-11102026),
con referencias IA exactas, corrección trazable de un marcador Docling y
selecciones manuales 149/150 sin promover el AST en cuarentena. No es una
validación de vigencia ni hay una arquitectura jurídica ganadora. Sigue vigente
el [protocolo experimental](SAT-GRAPH-EXPERIMENTS.md).

### Revisión posterior: extracción fiel y referencias completas

El dataset documental aislado utiliza **12 unidades de tres PDF oficiales**:
artículos 1–9 de Ley 30364 original, 149/150 de la copia Contraloría, y el reemplazo
citado de Ley 30364 art. 8 en el [DL 1323 original de El Peruano](https://busquedas.elperuano.pe/dispositivo/NL/1471010-2).
Este último PDF tiene 4 páginas y SHA256
`883ca8542867f3df0a636e27d65aaa52f9c652c4386a3a5bdb108d513f06fbf4`.
Se excluyen otras normas parciales del mismo archivo; la unidad elegida está en
PDF, p. 4 / página impresa 10. La compilación MIMP no integra este dataset de ranking.

Se detectó otro defecto real en Ley 30364 p. 2: Docling clasificó una continuación
del inciso 8 b como lista sin marcador y el exportador añadió un «3.» inexistente.
En una **copia** se reclasificó `#/texts/60` como TextItem. El builder verifica
hash/ref/fundamento, original y corrección, y prohíbe cambiar texto, `orig`, bbox,
página, charspan o cualquier otro campo. No permite eliminar un numeral real.
La copia `ley-30364-documentary-corrected.*` tiene 12241 caracteres frente a 12244
del export original. `ley-30364-original.*` permanece intacto.

El AST automático del Código Penal sigue en cuarentena. La revisión visual
PDF 67–68 seleccionó explícitamente los spans completos 149/150, excluyendo las
concordancias editoriales y artículos vecinos. Esos spans sirven como unidades
documentales IA, **no** como CTV jurídicos ni como un bypass del parser protegido.

`documentary-bundle-v1.json` liga PDF/Docling/Markdown por hashes, páginas, spans,
revisor y razones. El adaptador exige exportación Docling exacta y referencias
gold verificables. Usa `DocumentaryVersion`/`DocumentaryText`, no CTV/CLV aprobados;
selecciona `source_ids` explícitos y rechaza `as_of` normativo. La fecha de
publicación no se convierte en vigencia. El retriever SAT público ignora estos
nodos y la base canónica permanece fuera de esta evaluación.

Además, tres pérdidas de referencia eran cortes rígidos de 1000 caracteres, no
fallos de embedding. Se añadió una política natural **opt-in de investigación**
que conserva bytes/offsets, cota y ausencia de overlap. Mejoró la cobertura de
referencias BM25 development 80.77% → 100% sin API; no resuelve abstención semántica
ni demuestra generalización jurídica. Resultados, coste y heldout se consolidan
en el protocolo experimental existente para evitar dispersar más Markdown.

**Unidad de rollback:** retirar `structure_review.py`, el argumento documental
del parser/stage/CLI y sus tests/catalogación. No borrar SourceEvidence, Markdown,
PDF, parses previos ni revisiones jurídicas. Los artefactos versionados existentes
se leen sin recalcularlos con el parser nuevo.

### Revisión estructural v5: artículos, incisos y numerales oficiales

Se mantienen los 12 artículos del bundle v1, y en una **nueva** versión experimental
se añaden 33 componentes subordinados revisados visualmente contra los PDF oficiales:
Ley 30364 p. 1–2 y reemplazo citado de su art. 8 en DL 1323 p. 4. Son 45 DocumentaryVersion,
131 nodos y 168 aristas; 33 son `contains_version`. El artículo penal 149/150 no recibe
numerales inventados ni promoción automática de su AST. NotebookLM/legacy no entra.

La revisión detectó otras tres continuaciones mal clasificadas por Docling:
`#/texts/26`, 28 y 31 no tienen marcadores en PDF, p. 1. En otra copia se reclasifican
junto con 60, sin modificar texto/`orig`/geometría/proveniencia. Frente a la copia
corregida v1 solo desaparecen los prefijos generados «2. », «4. », «7. »: 12241 → 12232
caracteres. Originales, PDF, bundles/datasets previos permanecen intactos; el builder
actual conserva exactamente el snapshot v1, aunque admita campos nuevos.

Cada hijo conserva fuente, rango, hash, páginas y razón de revisión IA. Los
numerales 1–4 del art. 8 dependen de su **inciso d**. No se infiere la jerarquía a
partir del nivel Markdown ni se usa este sidecar como certificado de vigencia.
El contrato exige contención estricta, misma edición/recurso, rutas/tipos válidos
y hermanos disjuntos. No crea CTV ni fecha normativa ni incorpora el corpus al chat.

Se congelaron seis datasets y un plan de nueve ejecuciones antes de ver resultados.
La evaluación por raíz no duplica crédito de artículo/hijo, y la cobertura exige
el span efectivamente retornado. El contraste controlado muestra propagación real
pero regresión PPR en desarrollo; **no se recomienda activarlo por defecto**.
Resultados, comandos, hashes y rollback están consolidados en
[experimentos v5](SAT-GRAPH-EXPERIMENTS.md#membresías-oficiales-reales-y-ppr-controlado--v5).

**Verificación:** 150 pruebas focalizadas y 556 Python aprobadas/3 skipped opt-in/2 xfail;
nueve ensayos oficiales completos sin API nueva, fuentes/caché/ledger inalterados.
Sigue pendiente la abstención semántica y la eliminación de contexto solapado.
