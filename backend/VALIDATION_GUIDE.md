# VALIDATION_GUIDE.md

## Guía práctica del pipeline de validación — IA Jurídica

> Última actualización: Febrero 2026  
> Proyecto: `~/Documentos/IA_juridica/backend`

---

## 1. Qué es el pipeline de validación

Es un sistema que **revisa automáticamente** cada respuesta que genera el LLM (Cohere) antes de enviársela al usuario. Actúa como un inspector de calidad invisible.

Se activa en cada llamada a `POST /legal-query` y funciona en 4 pasos internos:

```
Respuesta del LLM
       │
       ▼
AntiHallucinationLayer   → ¿Inventó algo?
       │
       ▼
RAGCrossChecker          → ¿Tiene soporte en los documentos?
       │
       ▼
SelfCorrectionEngine     → Si hay problema: corregir (llama a Cohere de nuevo)
       │
       ▼
ValidationReport         → Informe final de calidad
```

---

## 2. Los 6 archivos y qué hace cada uno

### `validation/schemas.py`

Define los "moldes" de datos. No tiene lógica, solo estructuras.
No lo tocas directamente, pero todos los demás módulos lo usan.

```python
ValidatedResponse   # lo que sale del endpoint /legal-query
ValidationReport    # el informe de calidad dentro de la respuesta
ConfidenceLevel     # HIGH / MEDIUM / LOW
RAGChunk            # un fragmento del corpus con su score
ValidationStatus    # passed / warned / corrected / failed
```

---

### `validation/anti_hallucination.py`

Busca patrones de texto que indican que el modelo inventó algo.
Especializado en derecho peruano. No llama a ninguna API.

**Patrones que detecta:**
| Patrón | Ejemplo que detecta |
|---|---|
| `articulo_alto` | "artículo 9876 del Código Civil" |
| `ley_corta` | "Ley N° 12 establece..." |
| `monto_fijo_pension` | "la pensión mínima es de S/ 500" |
| `incertidumbre_legal` | "posiblemente el artículo aplicable sea..." |
| `casacion_incompleta` | "Casación 1234-25" (sin sala/región) |
| `entidad_inexistente` | "Tribunal Constitucional Federal" |
| `derogacion_no_verificada` | "fue derogado en 2020" (sin citar decreto) |
| `plazo_exacto_inventado` | "el proceso dura exactamente 90 días" |

**Parámetro clave:** `hallucination_threshold` en `main.py`

- Si `risk_score > threshold` → se activa self-correction
- Valor actual: `0.7` (bastante permisivo, puedes bajarlo a `0.4` para ser más estricto)

---

### `validation/cross_checker.py`

Compara la respuesta del LLM contra los documentos que ya tienes en memoria.
**No llama a Cohere.** Usa los 707 chunks que ya están cargados.

Divide la respuesta en oraciones y verifica si las palabras clave de cada oración
aparecen en el corpus. Si menos del 55% de las oraciones tienen soporte → `is_grounded: false`.

**Parámetro clave:** `cross_check_threshold`

- Valor actual: `0.55` (el 55% de las oraciones deben tener soporte)

---

### `validation/self_correction.py`

Si el `anti_hallucination` detecta un problema, este módulo le pide a Cohere
que reescriba la respuesta incluyendo los problemas detectados y el contexto RAG
como fuente de verdad. Máximo 2 reintentos.

**Cuándo se activa:** Solo cuando `risk_score > hallucination_threshold`  
**Cuándo NO se activa:** Con los valores actuales (threshold=0.7), casi nunca.
Si quieres que se active más seguido, baja el threshold.

---

### `validation/response_validator.py`

El orquestador. Es el único que llamas desde `main.py`.
Llama a los 3 módulos anteriores en orden y arma el informe final.

---

### `optimization/llm_optimizer.py`

Caché de respuestas + tracking de tokens. Vive en `app.state.llm_optimizer`.

- Guarda respuestas por hash SHA-256 del par `query|language`
- TTL: 3600 segundos (1 hora)
- Solo cachea respuestas con `is_reliable: true`
- Estima costo en USD por sesión

---

## 3. Cómo leer la respuesta del endpoint

Cuando llamas a `POST /legal-query`, la respuesta incluye el campo `validation`.
Aquí está cómo interpretarlo:

```json
"validation": {
  "status": "warned",
  "confidence": "low",
  "confidence_score": 0.4509,
  "hallucination_risk": 0.499,
  "is_grounded": true,
  "corrections_applied": 0,
  "flags": [],
  "cross_check": {
    "is_grounded": true,
    "overlap_score": 1,
    "ungrounded_claims": [],
    "supporting_chunks": ["..."]
  },
  "cultural_issues": ["Lenguaje demasiado complejo"],
  "warnings": [],
  "processing_time_ms": 118.6
}
```

### Campo por campo

| Campo                 | Qué significa                               | Valores posibles                       |
| --------------------- | ------------------------------------------- | -------------------------------------- |
| `status`              | Estado general de la validación             | `passed` `warned` `corrected` `failed` |
| `confidence`          | Nivel de confianza simplificado             | `high` `medium` `low`                  |
| `confidence_score`    | Score numérico de confianza                 | 0.0 a 1.0                              |
| `hallucination_risk`  | Riesgo de alucinación detectado             | 0.0 a 1.0                              |
| `is_grounded`         | ¿La respuesta tiene soporte en el corpus?   | `true` `false`                         |
| `corrections_applied` | Cuántas veces se autocorrigió               | 0, 1, 2                                |
| `flags`               | Lista de patrones de alucinación detectados | Lista de strings                       |
| `overlap_score`       | % de oraciones con soporte en RAG           | 0.0 a 1.0                              |
| `ungrounded_claims`   | Oraciones sin soporte en el corpus          | Lista de strings                       |
| `cultural_issues`     | Problemas de adecuación cultural            | Lista de strings                       |
| `processing_time_ms`  | Tiempo que tomó validar                     | Milisegundos                           |

### Qué significa cada `status`

```
passed    → Todo bien. Alta confianza, sin flags, sin problemas culturales.

warned    → La respuesta es usable pero tiene algo:
            - confidence baja (por rerank_scores bajos)
            - problemas culturales detectados
            - algún flag menor

corrected → Se detectó un problema y self-correction lo corrigió.
            La respuesta que ves ya fue reescrita.

failed    → confidence_score < 0.3. La respuesta no es confiable.
            Esto debería ser raro con el corpus actual.
```

---

## 4. Por qué `confidence` es `low` aunque la respuesta se vea bien

Este es el caso que estás viendo ahora. La fórmula de confianza es:

```
confidence_score = (rag_score × 0.40) + (anti_hallucination × 0.30) + (cross_check × 0.30)
```

El `rag_score` se calcula del promedio de `rerank_scores`. Con los valores que estás viendo:

```json
"rerank_scores": [0.025, 0.00014, 0.00006, 0.00005, 0.00002]
```

El promedio es aproximadamente `0.005`. Eso hace que el primer término de la fórmula
sea casi cero, y la confianza máxima posible ronde `0.50` sin importar qué tan buena sea la respuesta.

**La causa real:** Los documentos de violencia familiar en el corpus tienen pocos chunks
o no tienen suficiente densidad semántica. El reranker de Cohere no los encuentra relevantes.

**Cómo verificarlo:**

```bash
curl http://localhost:8000/documents | python3 -m json.tool
```

Busca cuántos chunks tienen los documentos de `violencia.md` y `Violencia_Psicológica...`.

---

## 5. Cómo ajustar los umbrales

Los umbrales están en `main.py` dentro del lifespan, en el bloque `ValidationConfig`:

```python
validation_config = ValidationConfig(
    hallucination_threshold=0.7,    # ← bajar para ser más estricto
    cross_check_threshold=0.55,     # ← bajar si quieres más tolerancia
    min_confidence_score=0.30,      # ← score mínimo antes de marcar FAILED
    max_self_correction_retries=2,  # ← cuántas veces intenta corregir
    enable_cross_check=True,
    enable_self_correction=True,
    enable_cultural_validation=True,
)
```

### Cuándo cambiar cada uno

**`hallucination_threshold`**

```
0.7 (actual) → muy permisivo, self-correction casi nunca se activa
0.4          → equilibrado, se activa cuando hay 1-2 flags
0.2          → muy estricto, se activa ante cualquier señal
```

**`cross_check_threshold`**

```
0.55 (actual) → el 55% de las oraciones deben tener soporte
0.35          → más tolerante, útil si el corpus es pequeño
0.75          → muy estricto, requiere alto soporte documental
```

**`min_confidence_score`**

```
0.30 (actual) → solo marca FAILED en casos extremos
0.50          → más exigente, marcará FAILED cuando rerank_scores son bajos
```

---

## 6. Correr los tests con `uv`

### Instalar dependencias de testing (solo la primera vez)

```bash
cd ~/Documentos/IA_juridica/backend
uv add pytest pytest-asyncio pytest-mock pytest-cov --dev
```

### Verificar que los módulos importan bien (hacer esto primero)

```bash
uv run python -c "from validation import ResponseValidator; print('OK')"
uv run python -c "from optimization import LLMOptimizer; print('OK')"
```

### Correr tests por módulo (de menor a mayor complejidad)

```bash
# 1. Optimizer (sin dependencias externas, más rápido)
uv run pytest tests/unit/test_llm_optimizer.py -v

# 2. Anti-hallucination (solo regex, offline)
uv run pytest tests/unit/test_anti_hallucination.py -v

# 3. Cross-checker (usa corpus en memoria)
uv run pytest tests/unit/test_cross_checker.py -v

# 4. Self-correction (usa mock de Cohere)
uv run pytest tests/unit/test_self_correction.py -v

# 5. Todos los unitarios juntos
uv run pytest tests/unit/ -v

# 6. Integración (pipeline completo con mocks)
uv run pytest tests/integration/ -v
```

### Ver cobertura de código

```bash
uv run pytest tests/unit/ --cov=validation --cov=optimization --cov-report=term-missing
```

La columna `MISS` indica qué líneas no están siendo probadas.

### Correr solo un test específico

```bash
# Por nombre del test
uv run pytest tests/unit/test_anti_hallucination.py::TestAntiHallucinationLayer::test_good_response_has_low_risk -v

# Por marcador
uv run pytest -m unit -v
uv run pytest -m integration -v
```

---

## 7. Problemas comunes y soluciones

### `ModuleNotFoundError: No module named 'validation'`

```bash
# Verificar que estás en la carpeta correcta
pwd  # debe mostrar .../backend

# Verificar que el venv está activo
which python  # debe apuntar al .venv del proyecto
```

### `fixture not found: mock_cohere_client`

El archivo `tests/conftest.py` no fue copiado o está en el lugar equivocado.
Debe estar en `backend/tests/conftest.py`, no dentro de `unit/` o `integration/`.

### `confidence: low` en todas las respuestas

Los `rerank_scores` son muy bajos. Ver sección 4 de esta guía.
Solución a largo plazo: agregar más documentos de violencia familiar al corpus.

### `status: warned` con `cultural_issues: ["Lenguaje demasiado complejo"]`

El `ContextEngineer` detecta que la respuesta usa lenguaje técnico para una zona
quechuahablante. No es un error del sistema, es una advertencia real. La respuesta
funciona pero podría simplificarse.

### Self-correction nunca se activa (`corrections_applied: 0` siempre)

El threshold actual es `0.7`. Para que se active necesitas un `risk_score > 0.7`,
lo que requiere múltiples patrones de alucinación simultáneos. Bajar el threshold a `0.4`
para que se active con más frecuencia.

---

## 8. El endpoint `/validation-stats`

```bash
curl http://localhost:8000/validation-stats | python3 -m json.tool
```

Úsalo para monitorear en tiempo real:

```json
{
  "optimizer": {
    "cache_hit_rate": 0.0,        ← ideal: > 0.3 (30% de consultas desde caché)
    "estimated_cost_usd": 0.000,  ← costo acumulado de la sesión
    "total_tokens": 0             ← tokens usados desde que arrancó el servidor
  },
  "rag_engine": {
    "total_documents": 16,        ← documentos en memoria
    "total_chunks": 707           ← fragmentos buscables
  },
  "validation_config": {
    "hallucination_threshold": 0.7,  ← umbrales activos
    "cross_check_threshold": 0.55,
    "min_confidence_score": 0.3
  }
}
```

**Señales de que el sistema está funcionando bien:**

- `cache_hit_rate` sube a medida que se repiten consultas similares
- `estimated_cost_usd` crece de forma proporcional al uso
- `total_documents` refleja los PDFs procesados

---

## 9. Dónde vive cada cosa en el código

```
backend/
├── main.py
│   ├── lifespan()          ← aquí se inicializa ResponseValidator y LLMOptimizer
│   ├── /legal-query        ← aquí se llama validator.validate()
│   ├── /upload-pdf         ← aquí se llama cross_checker.update_documents()
│   └── /validation-stats   ← aquí se leen las métricas
│
├── validation/
│   ├── schemas.py           ← tipos de datos (no tocar salvo para agregar campos)
│   ├── anti_hallucination.py ← agregar patrones aquí cuando detectes alucinaciones nuevas
│   ├── cross_checker.py     ← ajustar CLAIM_SUPPORT_THRESHOLD si hay muchos falsos negativos
│   ├── self_correction.py   ← ajustar el prompt de corrección si las correcciones no mejoran
│   └── response_validator.py ← ajustar _compute_confidence_score() si la fórmula no refleja realidad
│
├── optimization/
│   └── llm_optimizer.py    ← ajustar cache_ttl_seconds si las respuestas cambian frecuentemente
│
└── tests/
    ├── conftest.py          ← agregar fixtures cuando agregues tests nuevos
    ├── unit/                ← un archivo por módulo
    └── integration/         ← tests del pipeline completo
```

---

## 10. Agregar un patrón de alucinación nuevo

Cuando detectes que el LLM inventa algo de forma recurrente, agrégalo en
`validation/anti_hallucination.py` dentro de `LEGAL_HALLUCINATION_PATTERNS`:

```python
LEGAL_HALLUCINATION_PATTERNS = [
    # ... patrones existentes ...

    # Agregar al final:
    (
        r"tu_regex_aqui",
        "nombre_del_patron",
        "Descripción de qué detecta este patrón",
        0.40,   # severidad: 0.1 (leve) a 0.7 (grave)
    ),
]
```

Luego agregar el test correspondiente en `tests/unit/test_anti_hallucination.py`:

```python
@pytest.mark.parametrize("text,expected_flag", [
    # ... tests existentes ...
    ("texto que activa tu nuevo patrón", "nombre_del_patron"),
])
def test_individual_patterns_detected(self, anti_hallucination_layer, text, expected_flag):
    report = anti_hallucination_layer.analyze(text, rag_score=0.80)
    detected_names = [d["name"] for d in report.pattern_details]
    assert expected_flag in detected_names
```
