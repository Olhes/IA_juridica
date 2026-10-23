# Gold del harness de evaluación

Datos de evaluación versionados. **Ningún caso de esta carpeta es verdad jurídica verificada**:
los casos semilla son *candidatos* extraídos del corpus (`backend/docs/processed/`) y esperan
revisión humana.

| Archivo | Contenido | Estado |
|---|---|---|
| `legal_qa.v1.jsonl` | 107 preguntas (80 en español y 27 gemelos en quechua sureño enlazados por `parallel_id`) con hechos exigidos, afirmaciones prohibidas y citas aceptables | todos `candidate`, `reviewers: []`; el quechua espera revisión de un hablante nativo |
| `retrieval.v1.jsonl` | 80 casos de recuperación derivados de los casos en español | heredan el estado de `legal_qa` |
| `thresholds.v1.json` | Umbrales prerregistrados | `unregistered`: no se fija ningún número hasta medir un baseline |

## Cómo se construyó la semilla

`backend/evaluation/harness/seed_legal_qa.py` define los casos; cada hecho trae una **cita textual**
(`quote`) de un documento del corpus. El generador resuelve el segmento (`<doc_id>#<ordinal>`),
guarda su huella (`sha`) y falla si la cita no aparece. El cargador (`load_gold`) repite esa
verificación cada vez, de modo que un hecho inventado o un corpus que cambió rompen los tests.

```bash
cd backend && uv run python -m evaluation.harness.seed_legal_qa   # regenera legal_qa.v1.jsonl
```

El JSONL no se edita a mano: un test compara el archivo con lo que genera la definición.

## Esquema (`legal_qa/1`)

`id`, `version`, `status` (`candidate` → `reviewed` → `adjudicated`), `reviewers`, `topic`,
`query`, `language`, `stratum` (`positivo` | `limite` | `negativo`), `split` (`dev` | `holdout`),
`must_abstain`, `reference_segments`, `required_facts`, `forbidden_claims`,
`acceptable_citations`, `absent_terms`, `notes`.

- **Hecho exigido**: texto, cita de origen y *anclas* (AND de grupos; dentro de un grupo basta una
  alternativa; `re:` = expresión regular). Las anclas son una cota léxica conservadora; no sustituyen
  la lectura de un abogado ni la del juez.
- **Afirmación prohibida**: `contradicted` (el corpus dice lo contrario, con cita) o `unsupported`
  (el corpus no la respalda; sus patrones no deben aparecer en el corpus). Lleva un `example` que
  sus patrones deben detectar.
- **Negativo**: pregunta fuera del corpus; exige abstención y lista `absent_terms` que el cargador
  comprueba que no aparecen.
- **Adjudicado** exige dos revisores distintos, ciegos, que aprueban. Hasta entonces ningún
  resultado puede presentarse como métrica de lanzamiento.

## Limitaciones conocidas del corpus

Cuatro documentos (la Casación 1293-2021, el artículo de omisión de asistencia, el de pensión de
alimentos y el de tipos de tenencia) tienen OCR espaciado (más del 90 % de los tokens son una letra).
Las comparaciones usan `compact` (sin espacios ni puntuación) para poder citarlos, pero esos
documentos son pobres para la recuperación. El caso `violencia-tipos-ley-30364-art-8` los pone a prueba.
