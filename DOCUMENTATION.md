# IA Jurídica v2.0 - Documentación Técnica Completa

## 🎯 Descripción del Proyecto

Asistente virtual bilingüe (quechua-español) especializado en derecho familiar y procesamiento inteligente de documentos legales para comunidades andinas y rurales de América Latina.

**Tecnologías Clave:**
- **Docling**: Procesamiento avanzado de PDFs legales
- **LightRAG**: Motor RAG con grafos de conocimiento
- **Cohere**: Embeddings, reranking y generación de respuestas legales
- **Pydantic**: Validación estricta de respuestas estructuradas
- **DeepEval**: Evaluación automática de calidad
- **FastAPI**: API REST moderna
- **UV**: Gestión de dependencias ultrarrápida
- **Docker**: Contenerización para producción

## 🏗️ Arquitectura Técnica v2.0

### Monolito Modular Avanzado
- **Backend**: Python + FastAPI con servicios modulares
- **Procesamiento**: Docling para PDFs legales complejos
- **RAG**: LightRAG con grafos de conocimiento
- **Agentes**: Cohere + validación estricta con modelos Pydantic
- **Evaluación**: DeepEval para calidad garantizada
- **Frontend**: Next.js (App Router) con Tailwind CSS
- **Arquitectura Frontend**: Clean Architecture (`domain` / `application` / `infrastructure` / `presentation`)

### Estructura del Proyecto

```
ia-juridica/
├── backend/                       # 🚀 FastAPI + RAG + Docling
│   ├── main.py                    # API principal
│   ├── agents/                    # Agentes legales (Cohere + validación Pydantic)
│   ├── ingestion/                 # Pipelines de procesamiento PDF
│   ├── rag/                       # LightRAG y grafo de conocimiento
│   ├── evaluation/                # DeepEval
│   ├── config/                    # Settings y perfiles
│   ├── scripts/                   # Automatización CLI
│   ├── Dockerfile                 # Configuración Docker con UV
│   └── docs/                      # Artefactos locales (dev)
│       ├── raw_pdfs/
│       ├── processed/
│       ├── knowledge_graph/
│       └── failed/
├── frontend/                      # 🎨 Next.js App Router + TypeScript
│   ├── app/                       # Rutas y API routes (BFF)
│   │   ├── api/legal/consult/route.ts
│   │   ├── api/legal/pdf/route.ts
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── src/
│   │   ├── domain/                # Entidades/puertos
│   │   ├── application/           # Casos de uso
│   │   ├── infrastructure/        # Adaptadores HTTP/FastAPI
│   │   └── presentation/          # UI + componentes
│   └── package.json
├── pyproject.toml                 # Configuración UV y dependencias
├── uv.lock                        # Lock file UV (reproducción exacta)
├── requirements.txt               # Compatibilidad con pip
├── docker-compose.prod.yml         # Docker Compose producción
├── Dockerfile.temp                # Docker temporal (pip fallback)
├── package.json                   # Scripts raíz (frontend/backend)
├── README_SETUP.md
└── CLOUD_PDF_PIPELINE.md          # Arquitectura cloud para PDFs
```

## 📋 Requisitos

### Sistema
- **Python 3.12**
- **UV** - Gestor de dependencias ultrarrápido
- **Docker & Docker Compose** - Para producción
- **API Key de Cohere** (obligatoria)
- **8GB+ RAM** recomendado para procesamiento de PDFs

### Dependencias Principales
- `fastapi` - API REST
- `docling` - Procesamiento PDFs
- `lightrag` - Motor RAG
- `cohere` - Provider principal (LLM, embeddings, rerank)
- `pydantic` - Validación estructurada de respuestas
- `deepeval` - Evaluación calidad

## ⚡ Configuración Rápida con UV

### 1. Instalar UV
```bash
pip install uv
```

### 2. Setup Automático
```bash
cd ia-juridica
uv sync  # Instala todas las dependencias
```

### 3. Configurar Variables de Entorno
```bash
# Editar .env
COHERE_API_KEY=tu_api_key_aqui
SECRET_KEY=tu_secreto_unico_aqui
DEBUG=true
```

### 4. Iniciar Desarrollo
```bash
cd backend
uv run uvicorn main:app --reload --port 8000
```

### 5. Procesar PDFs
```bash
# Colocar PDFs en backend/docs/raw_pdfs/
uv run python scripts/process_pdfs.py process-dir
```

### 6. Iniciar Frontend
```bash
cd frontend
npm install
npm run dev
# Acceder: http://localhost:3000
```

## 🐳 Docker Producción

### Build y Deploy
```bash
# Construir imágenes
docker-compose -f docker-compose.prod.yml build

# Iniciar servicios
docker-compose -f docker-compose.prod.yml up -d

# Ver logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Arquitectura Docker
- **Backend**: Python 3.12-slim + UV + dependencias CPU-only
- **Frontend**: Next.js optimizado para producción
- **Volumes**: Persistencia para documentos y logs
- **Health checks**: Monitoreo automático de servicios

## 📡 Endpoints API v2.0

### 📄 Procesamiento de Documentos
- `POST /upload-pdf` - Subir y procesar PDF individual
- `POST /batch-process` - Procesar todos los PDFs en batch
- `GET /documents` - Listar documentos procesados
- `GET /knowledge-graph` - Obtener grafo de conocimiento

### ⚖️ Consultas Legales
- `POST /legal-query` - Consulta legal con RAG y agentes
- `POST /legal-query-stream` - Consulta legal con streaming token a token
- `POST /generate-pdf-report` - Generar informe PDF

### 🧪 Evaluación y Monitoreo
- `POST /evaluate-system` - Ejecutar evaluación completa
- `GET /health` - Health check del sistema

## 🔧 Variables de Entorno Completas

```env
# Servidor
APP_NAME=IA Jurídica
APP_VERSION=2.0.0
DEBUG=true
HOST=0.0.0.0
PORT=8000

# Cohere (OBLIGATORIO)
COHERE_API_KEY=tu_api_key_cohere_aqui
COHERE_EMBED_MODEL=embed-multilingual-v3.0
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
COHERE_LLM_MODEL=command-r7b-12-2024
COHERE_MAX_TOKENS=2048
COHERE_TEMPERATURE=0.3

# Base de Datos
DATABASE_URL=sqlite:///./juridica.db
DATABASE_PATH=./database/juridica.db

# Documentos
DOCS_ROOT_DIR=./docs
RAW_PDF_DIR=./backend/docs/raw_pdfs
PROCESSED_DIR=./backend/docs/processed
KNOWLEDGE_GRAPH_DIR=./backend/docs/knowledge_graph

# RAG
RAG_ENGINE=lightrag
EMBEDDING_MODEL=embed-multilingual-v3.0
EMBEDDING_DIM=1024
EMBEDDING_BATCH_SIZE=96
MAX_CHUNK_SIZE=1000

# Evaluación
EVALUATION_ENABLED=true
DEEPEVAL_API_KEY=tu_api_key_deepeval
EVALUATION_THRESHOLD=0.7

# Seguridad
SECRET_KEY=tu_secreto_unico_aqui
JWT_ALGORITHM=HS256
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=900

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/juridica.log
```

## 🧠 Servicios Core v2.0

### 📄 DoclingProcessor (`backend/ingestion/docling_processor.py`)
**Propósito:** Extraer estructura legal inteligente de PDFs
- **Funciones clave:** `process_pdf()`, `_extract_legal_structure()`, `_to_legal_markdown()`
- **Características:** OCR, detección de tablas, extracción de artículos/secciones
- **Salida:** Markdown estructurado con metadatos legales

### 🤖 LegalAgent (`backend/agents/pydantic_agents.py`)
**Propósito:** Generar respuestas legales con Cohere y validación estructurada
- **Modelos:** `ViolenceResponse`, `PensionResponse`, `GeneralLegalResponse`
- **LLM provider:** Cohere `command-r7b-12-2024`
- **Validación:** Estructura Pydantic estricta
- **Bilingüe:** Respuestas simultáneas en español y quechua

### 🔍 LightRAGEngine (`backend/rag/lightrag_engine.py`)
**Propósito:** Motor RAG con grafos de conocimiento
- **Funciones:** `query()`, `add_document()`, `get_knowledge_graph()`, `_extract_relevant_fragment()`
- **Características:** Búsqueda semántica + relaciones entre conceptos
- **Indexación:** Automática con embeddings y metadatos
- **Modo Fallback:** Búsqueda por palabras clave cuando LightRAG no está disponible
- **Fuentes:** Extracción de metadatos desde `doc_storage` de LightRAG

### 🧪 DeepEvalTests (`backend/evaluation/deepeval_tests.py`)
**Propósito:** Evaluación automática de calidad de respuestas
- **Métricas:** Relevancia, sesgo, alucinaciones, fidelidad
- **Testing:** Casos de prueba legales predefinidos
- **Reportes:** Markdown y JSON con resultados detallados

### ⚙️ Settings (`backend/config/settings.py`)
**Propósito:** Configuración centralizada con validación
- **Validación:** Automática de variables críticas
- **Tipado:** Pydantic para seguridad de tipos
- **Entornos:** Desarrollo y producción diferenciados

### ⚡ UV Integration
**Propósito:** Gestión de dependencias ultrarrápida
- **pyproject.toml:** Configuración moderna de dependencias
- **uv.lock:** Reproducción exacta de ambientes
- **Rendimiento:** 10x más rápido que pip tradicional
- **Docker:** Integración nativa para contenedores ligeros

## 📊 Flujo de Datos Completo

### 🔄 Procesamiento de Documentos
```
PDF (local o cloud) → Docling → Markdown estructurado → LightRAG → Grafo de conocimiento
        ↓                ↓               ↓                 ↓               ↓
   upload/pipeline   docling_processor   processed md     add_document     knowledge_graph
```

### 🤖 Flujo de Consulta Legal v2.0 (con Context Engineering)
```
Usuario → Next.js UI → Use Case/Gateway → API Route Next (BFF) → FastAPI /legal-query
    ↓           ↓             ↓                 ↓                     ↓
Render UI   Validación TS   /api/legal/*    Normalización payload   RAG + Agente + fuentes

Respuesta FastAPI → API Route Next → UI bilingüe (spanish/quechua)
```

### ⚡ Flujo UV + Docker
```
Desarrollo: uv sync → uv run uvicorn → Desarrollo rápido
Producción: Docker build → uv sync --frozen → Contenedor optimizado
    ↓              ↓                    ↓
pyproject.toml → .venv/ → Imagen Docker ligera
```

## 📋 Temas Legales Soportados

### 🚨 Violencia Familiar
- **Leyes:** Ley 30364, Código Civil
- **Agentes:** `ViolenceResponse` con niveles de urgencia
- **Recursos:** Línea 113, comisarias, refugios

### 💰 Pensión de Alimentos
- **Leyes:** Código Civil artículos 472-485
- **Agentes:** `PensionResponse` con cálculos básicos
- **Proceso:** Pasos judiciales, documentos requeridos

### 🛡️ Medidas de Protección
- **Leyes:** Ley 30364 Artículo 20
- **Agentes:** Respuestas inmediatas con recursos locales
- **Urgencia:** Procedimientos 24/7

### 👨‍👩‍👧‍👦 Régimen de Visitas y Tenencia
- **Leyes:** Código Civil, derechos parentales
- **Agentes:** `GeneralLegalResponse` bilingüe
- **Proceso:** Juzgados de Familia, horarios

## 📁 Gestión de Documentos

### 📄 PDFs Recomendados
- **Códigos legales:** Civil, Penal, Procesal
- **Leyes específicas:** 30364, 28806, etc.
- **Formatos judiciales:** Demandas, denuncias
- **Jurisprudencia:** Sentencias relevantes
- **Documentos gubernamentales:** Reglamentos, directivas

### 🔄 Estados de Procesamiento
```
backend/docs/raw_pdfs/ → backend/docs/processed/ → backend/docs/knowledge_graph/
     ↓                    ↓                      ↓
PDFs sin procesar   Markdown estructurado   Grafo de conocimiento
```

### ❌ Manejo de Errores
- **backend/docs/failed/** - PDFs con problemas de procesamiento
- **Reprocesamiento:** `python scripts/process_pdfs.py reprocess`
- **Validación:** `python scripts/process_pdfs.py validate`

## 📊 Base de Datos y Almacenamiento

### 🗄️ SQLite (Base de Datos Principal)
- **legal_queries** - Consultas procesadas con metadatos
- **daily_stats** - Estadísticas de uso y rendimiento
- **popular_topics** - Temas más consultados
- **error_logs** - Registro detallado de errores

### 📁 Sistema de Archivos
- **backend/docs/raw_pdfs/** - PDFs originales sin procesar (solo desarrollo local)
- **backend/docs/processed/** - Markdown estructurado por Docling (artefacto local)
- **backend/docs/knowledge_graph/** - Grafo de conocimiento LightRAG (artefacto local)
- **backend/docs/failed/** - PDFs con errores de procesamiento
- **Producción recomendada:** mover estos artefactos a object storage (S3/GCS/R2)

### 🕸️ Grafo de Conocimiento
- **Nodos:** Artículos, leyes, conceptos legales
- **Relaciones:** "aplica_a", "relaciona_con", "sanciona"
- **Métricas:** Centralidad, relevancia, frecuencia

## ☁️ Arquitectura Cloud para PDFs (sin subir PDFs al repo)

### Objetivo
Evitar versionar PDFs en Git y mover ingestión/procesamiento a servicios administrados.

### Diseño recomendado
1. **Object Storage:** S3 / GCS / Azure Blob / Cloudflare R2 para almacenar PDFs y salidas (`raw`, `processed`, `failed`).
2. **Upload seguro:** frontend solicita URL firmada (`presigned URL`) y sube directo al bucket.
3. **Cola de procesamiento:** SQS / Pub/Sub / RabbitMQ / Cloud Tasks con mensajes `document_id`.
4. **Worker de ingestión:** servicio Python (mismo código Docling + LightRAG) que descarga del bucket, procesa y persiste metadatos.
5. **Estado y trazabilidad:** PostgreSQL para `document_status`, hashes, errores y tiempos.
6. **FastAPI como orquestador:** expone endpoints para crear uploads, consultar estado y disparar reprocesamiento.

### Flujo propuesto
```text
Frontend -> FastAPI /documents/presign-upload -> URL firmada
Frontend -> Object Storage (PUT PDF)
Object Storage Event -> Queue
Worker Python -> descarga PDF -> Docling -> LightRAG -> guarda resultados
Worker -> actualiza PostgreSQL -> FastAPI expone estado para UI
```

### Contratos API sugeridos
- `POST /documents/presign-upload` -> entrega `upload_url` + `document_id`
- `POST /documents/ingest-from-object` -> encola procesamiento por `document_id`
- `GET /documents/{document_id}/status` -> `uploaded|processing|processed|failed`
- `POST /documents/{document_id}/reprocess` -> reprocesamiento controlado

### Ventajas
- Repositorio liviano y limpio (sin PDFs pesados)
- Escalabilidad horizontal de workers
- Menor riesgo de fuga de información por commits accidentales
- Mejor observabilidad del pipeline de documentos

## 🔒 Seguridad y Validación

### 🛡️ Seguridad de API
- **Rate Limiting:** recomendado en API Gateway/Load Balancer (producción)
- **Validación:** entrada tipada con Pydantic en FastAPI
- **CORS:** configurado en FastAPI (restringir orígenes en producción)
- **Autenticación:** JWT/API key opcional según perfil de despliegue
- **Storage cloud:** usar URLs firmadas para evitar exponer credenciales

### ✅ Validación de Datos
- **Pydantic Models:** Estructura estricta para todas las respuestas
- **Tipado:** Sin tipos dinámicos, todo validado
- **Sanitización:** Limpieza automática de entrada
- **Errores:** Manejo estructurado con logging

### 🧪 Evaluación Continua
- **DeepEval:** Testing automático de calidad
- **Métricas:** Relevancia (≥0.7), Sesgo (≤0.3), Alucinaciones (≤0.3)
- **Casos de Prueba:** Violencia, pensión, medidas, visitas
- **Reportes:** Automáticos en JSON y Markdown

## 🌐 Despliegue y Producción

### 🚀 Configuración de Producción
```bash
# Variables críticas
DEBUG=false
SECRET_KEY=tu_secreto_muy_seguro
RATE_LIMIT_ENABLED=true
LOG_LEVEL=WARNING
```

### 📦 Requisitos de Producción
- **Python 3.12**
- **8GB+ RAM** (para procesamiento de PDFs)
- **50GB+ Disco** (para documentos y grafo)
- **Cohere API Key** (obligatoria)

### 🐳 Docker (Opcional)
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
```

### ☁️ Plataformas Recomendadas
- **Frontend:** Vercel / Netlify
- **Backend FastAPI:** Railway / Render / Fly.io / DigitalOcean
- **Documentos:** AWS S3 / Google Cloud Storage / Cloudflare R2
- **Cola:** SQS / Pub/Sub / RabbitMQ
- **Base de Datos:** PostgreSQL (producción), SQLite (desarrollo)

## 📈 Monitoreo y Métricas

### 📊 Endpoints de Monitoreo
- `GET /health` - Estado general del sistema
- `POST /evaluate-system` - Evaluación completa
- `GET /knowledge-graph` - Datos del grafo

### 📋 Métricas Clave
- **Procesamiento:** PDFs procesados, tasa de éxito
- **Consultas:** Tiempo respuesta, relevancia
- **Calidad:** Puntajes DeepEval, tasa de aprobación
- **Recursos:** Uso de CPU, memoria, disco

### 📝 Logging Estructurado
- **Niveles:** DEBUG, INFO, WARNING, ERROR
- **Formato:** JSON con timestamp y contexto
- **Rotación:** Automática por tamaño y tiempo
- **Archivos:** `logs/juridica.log`

## � Optimización de Rendimiento v2.0

### ⚡ Pipeline Optimizado (`backend/ingestion/optimized_pipeline.py`)
**Propósito:** Procesamiento paralelo de PDFs con control de concurrencia
- **Speedup:** 4-8x más rápido que el pipeline original
- **Workers:** Configurables según hardware (auto-detección)
- **Cache:** Evita reprocesamiento de archivos sin cambios
- **Control:** Semáforos para limitar uso de recursos

### 💾 Cache Inteligente (`backend/ingestion/cache_manager.py`)
**Propósito:** Sistema de cache para evitar reprocesamiento
- **Hash verification:** MD5 para detectar cambios en PDFs
- **Metadata storage:** JSON con timestamps y estados
- **Selective processing:** Solo procesa archivos modificados
- **Performance:** 0.01s para archivos ya procesados

### 🎯 Procesamiento Selectivo (`backend/ingestion/selective_processor.py`)
**Propósito:** Elección específica de documentos a procesar
- **Por categorías:** `pension_alimentos`, `violencia_familiar`, etc.
- **Por palabras clave:** `guía`, `manual`, `formulario`
- **Archivos específicos:** Lista exacta de nombres
- **Por lotes:** Control de número de archivos

### 📦 Procesamiento por Lotes (`backend/ingestion/batch_processor.py`)
**Propósito:** Manejo eficiente de grandes volúmenes (1000+ PDFs)
- **Batch size:** Configurable (50-100 archivos por lote)
- **Memory management:** Control de uso de RAM
- **Progress tracking:** Estadísticas por lote
- **Error recovery:** Reintentos automáticos

### ⚙️ Configuración de Rendimiento (`backend/config/performance_settings.py`)
**Propósito:** Auto-optimización según hardware
- **CPU detection:** Ajuste automático de workers
- **Memory limits:** Límites según RAM disponible
- **Timeout settings:** Configurables por tipo de PDF
- **Profiles:** `development`, `production`, `high_performance`

### 📈 Escalabilidad (`backend/config/scalability_settings.py`)
**Propósito:** Configuración para grandes volúmenes
- **1000+ PDFs:** Requisitos y costos estimados
- **Database scaling:** PostgreSQL vs SQLite
- **Vector database:** Pinecone/Weaviate para producción
- **Cloud storage:** S3/Google Cloud integration

## 🎮 Scripts de Procesamiento Selectivo

### 🖥️ Procesamiento Interactivo (`backend/selective_processing.py`)
**Menú interactivo para elegir qué procesar:**
```bash
py selective_processing.py
# Opciones:
# 1. Por categorías
# 2. Por palabras clave  
# 3. Archivos específicos
# 4. Primeros N archivos
# 5. Desarrollo rápido (8 esenciales)
```

### ⚡ Comandos Rápidos (`backend/quick_process.py`)
**Comandos directos sin interacción:**
```bash
py quick_process.py --essentials          # 8 archivos esenciales
py quick_process.py --category pension_alimentos  # Solo pensiones
py quick_process.py --first 5             # Primeros 5 archivos
py quick_process.py --guides              # Solo guías y manuales
```

### 🧪 Pruebas de Rendimiento
- **`test_optimized_pipeline.py`** - Benchmark del pipeline optimizado
- **`test_real_performance.py`** - Pruebas con PDFs reales
- **`estimate_1000_pdfs.py`** - Estimación de escala y costos

## 📊 Métricas de Rendimiento

### ⚡ Mejoras de Velocidad
| Operación | Original | Optimizado | Speedup |
|------------|-----------|-------------|----------|
| **21 PDFs (cache)** | 2-3 min | 0.01s | **18,000x** |
| **21 PDFs (nuevos)** | 30-45 min | 5-8 min | **4-6x** |
| **1000 PDFs** | 8-12 horas | 1-2 horas | **6-8x** |

### 💾 Uso de Recursos
| Componente | Uso Original | Uso Optimizado |
|------------|--------------|-----------------|
| **CPU** | 100% (1 core) | 400% (4 cores) |
| **RAM** | 2-4GB | 4-8GB (controlado) |
| **I/O** | Secuencial | Paralelo |

### 🎯 Configuración Recomendada por Volumen

| PDFs | Workers | RAM | Tiempo | Costo/mes |
|-------|---------|------|--------|-----------|
| **1-50** | 4 | 8GB | 1-2 min | $50 |
| **50-500** | 8 | 16GB | 5-10 min | $100 |
| **500-1000** | 16 | 32GB | 15-30 min | $200 |
| **1000+** | 16+ | 64GB | 1-2 horas | $300+ |

## �🛠️ Scripts y Automatización

### ⚙️ Script de Configuración (`scripts/setup.py`)
```bash
python scripts/setup.py
# ✅ Valida configuración
# ✅ Crea directorios
# ✅ Instala dependencias
# ✅ Verifica componentes
# ✅ Inicializa base de datos
# ✅ Detecta hardware y optimiza
```

### 📄 Procesamiento de PDFs (`scripts/process_pdfs.py`)
```bash
# Procesamiento tradicional (todos)
# Procesar directorio completo
python scripts/process_pdfs.py process-dir

# Ver estadísticas
python scripts/process_pdfs.py stats

# Validar procesados
python scripts/process_pdfs.py validate

# Reprocesar fallidos
python scripts/process_pdfs.py reprocess
```

## 🧪 Ejemplos de Uso

### 📄 Subir y Procesar PDF
```bash
# Método 1: API
curl -X POST "http://localhost:8000/upload-pdf" -F "file=@ley_30364.pdf"

# Método 2: CLI
cp ley_30364.pdf backend/docs/raw_pdfs/
python scripts/process_pdfs.py process-dir
```

### ⚖️ Consulta Legal
```bash
curl -X POST "http://localhost:8000/legal-query" \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Qué hago si mi pareja me golpea?", "language": "spanish"}'
```

### 🧪 Evaluación del Sistema
```bash
curl -X POST "http://localhost:8000/evaluate-system"
# Retorna: puntuación, métricas, recomendaciones
```

## 🔧 Solución de Problemas Comunes

### ❌ "COHERE_API_KEY no configurada"
```bash
# Editar .env
COHERE_API_KEY=...
# Reiniciar servidor
python main.py
```

### ❌ "Docling no disponible"
```bash
# Reinstalar dependencias
pip install docling --force-reinstall
```

### ❌ "PDF corrupto"
```bash
# Mover a failed y reprocesar
python scripts/process_pdfs.py reprocess
```

### ❌ "Baja calidad en respuestas"
```bash
# Ejecutar evaluación
curl -X POST "http://localhost:8000/evaluate-system"
# Revisar métricas y ajustar prompts
```

## 📚 Referencias y Recursos

### 📖 Documentación Adicional
- **README_SETUP.md** - Guía de configuración rápida
- **CLOUD_PDF_PIPELINE.md** - Diseño de almacenamiento/procesamiento cloud de PDFs
- **API Docs** - `http://localhost:8000/docs` (Swagger)
- **DeepEval** - Documentación de evaluación
- **Docling** - Guía de procesamiento PDF

### 🔗 Enlaces Útiles
- **Cohere API** - https://dashboard.cohere.com/
- **LightRAG** - https://github.com/HKUDS/LightRAG
- **Pydantic** - https://docs.pydantic.dev/
- **FastAPI** - https://fastapi.tiangolo.com/

---

## 🎯 Resumen de Cambios v2.0

### 🔄 Arquitectura Actualizada
- **Node.js → Python + FastAPI**
- **LLM básico → Docling + LightRAG + Cohere (embed/rerank/chat) + validación Pydantic**
- **Monolito básico → Monolito modular avanzado**

### 🚀 Nuevas Capacidades
- **Procesamiento inteligente de PDFs** con Docling
- **RAG con grafos de conocimiento** con LightRAG
- **Agentes validados** con modelos Pydantic
- **Evaluación automática** con DeepEval
- **Scripts de automatización** completos

### 📈 Mejoras de Calidad
- **Respuestas estructuradas** sin alucinaciones
- **Validación automática** de cada respuesta
- **Testing continuo** de calidad del sistema
- **Monitoreo detallado** de métricas

---

**🎉 IA Jurídica v2.0: Sistema legal bilingüe con procesamiento inteligente de documentos y calidad garantizada.**
informacion en pdf sobre

-sobre Violencia Física o Psicológica
-Pensión de Alimentos(Omisión a la Asistencia)
-Medidas de protección
-Régimen de Visitas y Tenencia
-Denuncias y Procesos Judiciales
-Filiación (Reconocimiento de hijos): En zonas rurales hay muchos casos de niños no reconocidos legalmente, lo que impide pedir alimentos.
-Derecho a la Identidad (DNI): Sin DNI no hay proceso judicial. Es la base de todo.

individualmente lo maximo posible

con estos requisitos de documentacion:

- Normativa simplificada (artículos clave en lenguaje claro)
- Guías procesales (pasos concretos)
- Formatos y modelos (demandas, denuncias)
- Jurisprudencia relevante (casos similares)
- Directorios institucionales (dónde denunciar)

## 🔄 Flujo de Desarrollo Recomendado

### 🚀 Fase 1: Desarrollo Rápido
```bash
# 1. Procesar solo archivos esenciales (8 PDFs)
python quick_process.py --essentials
# Tiempo: 1-2 minutos

# 2. Iniciar servidor de desarrollo
python main.py
# http://localhost:8000
```

### 📈 Fase 2: Expansión Controlada
```bash
# 1. Añadir por categorías
python quick_process.py --category pension_alimentos
python quick_process.py --category violencia_familiar
# Tiempo: 2-3 minutos por categoría

# 2. Validar calidad
python scripts/process_pdfs.py validate
```

### 🏭 Fase 3: Producción
```bash
# 1. Procesamiento completo optimizado
python test_optimized_pipeline.py

# 2. Evaluación final
python scripts/evaluate_system.py

# 3. Configuración de producción
DEBUG=false
python main.py --prod
```

## 📋 Resumen de Mejoras v2.0

### ⚡ Optimizaciones Implementadas
- ✅ **Pipeline paralelo** - 4-8x más rápido
- ✅ **Cache inteligente** - 18,000x para archivos procesados
- ✅ **Procesamiento selectivo** - Elección específica de documentos
- ✅ **Auto-configuración** - Detección automática de hardware
- ✅ **Control de recursos** - Límites de memoria y CPU
- ✅ **Escalabilidad** - Soporte para 1000+ PDFs
- ✅ **Monitoreo** - Métricas en tiempo real
- ✅ **Error recovery** - Reintentos automáticos
- ✅ **Batch processing** - Manejo de grandes volúmenes

### 🎯 Beneficios Clave
- **Velocidad:** 4-8x más rápido que el original
- **Eficiencia:** 0.01s para archivos ya procesados
- **Control:** Elección exacta de qué procesar
- **Escalabilidad:** Hasta 10,000+ PDFs con configuración adecuada
- **Desarrollo:** Iteraciones rápidas con subsets de datos
- **Producción:** Robusto para volúmenes grandes

### 🚀 Próximos Pasos
1. **Ingesta cloud de PDFs** - Upload firmado + cola + workers Python
2. **PostgreSQL en producción** - Estado de documentos, auditoría y métricas
3. **Vector DB gestionada (opcional)** - Pinecone/Weaviate/Qdrant para mayor escala
4. **Observabilidad** - métricas y trazas (Grafana/Prometheus/OpenTelemetry)
5. **Hardening de seguridad** - CORS restringido, rate limits y auth por entorno

---

**📞 Soporte y Contribuciones**
- **Issues:** GitHub Repository
- **Documentación:** `DOCUMENTATION.md`
- **Testing:** `backend/test_optimized_pipeline.py`
- **Configuración:** `backend/config/performance_settings.py`

**🎯 IA Jurídica v2.0 - Asistente Legal Bilingüe Optimizado**
