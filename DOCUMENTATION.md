# IA Jurídica v2.0 - Documentación Técnica Completa

## 🎯 Descripción del Proyecto

Asistente virtual bilingüe (quechua-español) especializado en derecho familiar y procesamiento inteligente de documentos legales para comunidades andinas y rurales de América Latina.

**Tecnologías Clave:**
- **Docling**: Procesamiento avanzado de PDFs legales
- **LightRAG**: Motor RAG con grafos de conocimiento
- **Pydantic AI**: Agentes con respuestas estructuradas y validadas
- **DeepEval**: Evaluación automática de calidad
- **FastAPI**: API REST moderna

## 🏗️ Arquitectura Técnica v2.0

### Monolito Modular Avanzado
- **Backend**: Python + FastAPI con servicios modulares
- **Procesamiento**: Docling para PDFs legales complejos
- **RAG**: LightRAG con grafos de conocimiento
- **Agentes**: Pydantic AI con validación estricta
- **Evaluación**: DeepEval para calidad garantizada
- **Frontend**: React SPA con Tailwind CSS

### Estructura del Proyecto

```
ia-juridica/
├── docs/                      # 📄 Datos y documentos
│   ├── raw_pdfs/             # PDFs legales sin procesar
│   ├── processed/            # Markdown estructurado (salida Docling)
│   ├── knowledge_graph/      # Grafo de conocimiento LightRAG
│   └── failed/               # PDFs con errores
├── backend/                   # 🚀 API y servicios core
│   ├── main.py               # Servidor FastAPI principal
│   ├── ingestion/            # Procesamiento de documentos
│   │   ├── docling_processor.py    # ⭐ Núcleo Docling
│   │   └── pipeline.py             # Orquestación batch
│   ├── agents/               # 🤖 Agentes de IA validados
│   │   └── pydantic_agents.py      # Respuestas estructuradas
│   ├── rag/                  # 🔍 Motor RAG avanzado
│   │   └── lightrag_engine.py      # Grafos de conocimiento
│   ├── evaluation/           # 🧪 Evaluación de calidad
│   │   └── deepeval_tests.py       # Testing automático
│   ├── config/               # ⚙️ Configuración centralizada
│   │   └── settings.py             # Variables de entorno
│   ├── utils/                # 🛠️ Utilidades
│   │   └── file_utils.py           # Manejo de archivos
│   └── scripts/              # 📜 Scripts de automatización
│       ├── setup.py                # Configuración inicial
│       └── process_pdfs.py         # Procesamiento CLI
├── frontend/                  # 🎨 Interfaz web
│   ├── src/components/       # Componentes React
│   └── public/               # Assets estáticos
├── requirements.txt           # 📦 Dependencias Python
└── README_SETUP.md           # 📖 Guía rápida
```

## 📋 Requisitos

### Sistema
- **Python 3.9+**
- **API Key de OpenAI** (obligatoria)
- **8GB+ RAM** recomendado para procesamiento de PDFs

### Dependencias Principales
- `fastapi` - API REST
- `docling` - Procesamiento PDFs
- `lightrag` - Motor RAG
- `pydantic-ai` - Agentes validados
- `deepeval` - Evaluación calidad

## � Configuración Rápida

### 1. Setup Automático
```bash
cd ia-juridica/backend
python scripts/setup.py
```

### 2. Configurar Variables de Entorno
```bash
# Editar .env
OPENAI_API_KEY=tu_api_key_aqui
SECRET_KEY=tu_secreto_unico_aqui
DEBUG=true
```

### 3. Procesar PDFs
```bash
# Colocar PDFs en docs/raw_pdfs/
python scripts/process_pdfs.py process-dir
```

### 4. Iniciar Servidor
```bash
python main.py
# Acceder: http://localhost:8000
```

## 📡 Endpoints API v2.0

### 📄 Procesamiento de Documentos
- `POST /upload-pdf` - Subir y procesar PDF individual
- `POST /batch-process` - Procesar todos los PDFs en batch
- `GET /documents` - Listar documentos procesados
- `GET /knowledge-graph` - Obtener grafo de conocimiento

### ⚖️ Consultas Legales
- `POST /legal-query` - Consulta legal con RAG y agentes
- `POST /generate-pdf-report` - Generar informe PDF
- `POST /validate-query` - Validar consulta legal

### 🧪 Evaluación y Monitoreo
- `POST /evaluate-system` - Ejecutar evaluación completa
- `GET /health` - Health check del sistema
- `GET /stats` - Estadísticas de procesamiento

### 🌐 Idioma y Traducción
- `POST /language/detect` - Detectar idioma del texto
- `POST /translate` - Traducir entre quechua/español

## 🔧 Variables de Entorno Completas

```env
# Servidor
APP_NAME=IA Jurídica
APP_VERSION=2.0.0
DEBUG=true
HOST=0.0.0.0
PORT=8000

# OpenAI (OBLIGATORIO)
OPENAI_API_KEY=tu_api_key_aqui
OPENAI_MODEL=gpt-4
OPENAI_MAX_TOKENS=1500
OPENAI_TEMPERATURE=0.7

# Base de Datos
DATABASE_URL=sqlite:///./juridica.db
DATABASE_PATH=./database/juridica.db

# Documentos
DOCS_ROOT_DIR=./docs
RAW_PDF_DIR=./docs/raw_pdfs
PROCESSED_DIR=./docs/processed
KNOWLEDGE_GRAPH_DIR=./docs/knowledge_graph

# RAG
RAG_ENGINE=lightrag
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=768
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

### 🤖 PydanticAgents (`backend/agents/pydantic_agents.py`)
**Propósito:** Generar respuestas legales estructuradas y validadas
- **Modelos:** `ViolenceResponse`, `PensionResponse`, `GeneralLegalResponse`
- **Validación:** Estructura Pydantic estricta, sin alucinaciones
- **Bilingüe:** Respuestas simultáneas en español y quechua

### 🔍 LightRAGEngine (`backend/rag/lightrag_engine.py`)
**Propósito:** Motor RAG con grafos de conocimiento
- **Funciones:** `query()`, `add_document()`, `get_knowledge_graph()`
- **Características:** Búsqueda semántica + relaciones entre conceptos
- **Indexación:** Automática con embeddings y metadatos

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

## 📊 Flujo de Datos Completo

### 🔄 Procesamiento de Documentos
```
PDF Crudo → Docling → Markdown Estructurado → LightRAG → Grafo de Conocimiento
    ↓           ↓              ↓                ↓              ↓
docs/raw_pdfs → docling_processor.py → docs/processed → lightrag_engine.py → knowledge_graph/
```

### 🤖 Flujo de Consulta Legal
```
Usuario → API → RAG Engine → Pydantic Agent → DeepEval → Respuesta Validada
    ↓        ↓        ↓           ↓            ↓           ↓
Frontend → main.py → lightrag_engine.py → pydantic_agents.py → deepeval_tests.py → JSON Response
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
docs/raw_pdfs/     → docs/processed/     → docs/knowledge_graph/
     ↓                    ↓                      ↓
PDFs sin procesar   Markdown estructurado   Grafo de conocimiento
```

### ❌ Manejo de Errores
- **docs/failed/** - PDFs con problemas de procesamiento
- **Reprocesamiento:** `python scripts/process_pdfs.py reprocess`
- **Validación:** `python scripts/process_pdfs.py validate`

## 📊 Base de Datos y Almacenamiento

### 🗄️ SQLite (Base de Datos Principal)
- **legal_queries** - Consultas procesadas con metadatos
- **daily_stats** - Estadísticas de uso y rendimiento
- **popular_topics** - Temas más consultados
- **error_logs** - Registro detallado de errores

### 📁 Sistema de Archivos
- **docs/raw_pdfs/** - PDFs originales sin procesar
- **docs/processed/** - Markdown estructurado por Docling
- **docs/knowledge_graph/** - Grafo de conocimiento LightRAG
- **docs/failed/** - PDFs con errores de procesamiento

### 🕸️ Grafo de Conocimiento
- **Nodos:** Artículos, leyes, conceptos legales
- **Relaciones:** "aplica_a", "relaciona_con", "sanciona"
- **Métricas:** Centralidad, relevancia, frecuencia

## 🔒 Seguridad y Validación

### 🛡️ Seguridad de API
- **Rate Limiting:** 100 requests por IP cada 15 minutos
- **Validación:** Entrada sanitizada con Pydantic
- **Headers:** Helmet para seguridad HTTP
- **JWT:** Autenticación opcional con tokens

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
- **Python 3.9+**
- **8GB+ RAM** (para procesamiento de PDFs)
- **50GB+ Disco** (para documentos y grafo)
- **OpenAI API Key** (obligatoria)

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
- **Backend:** Railway, Heroku, DigitalOcean
- **Documentos:** AWS S3, Google Cloud Storage
- **Base de Datos:** PostgreSQL (producción), SQLite (desarrollo)

## 📈 Monitoreo y Métricas

### 📊 Endpoints de Monitoreo
- `GET /health` - Estado general del sistema
- `GET /stats` - Estadísticas de procesamiento
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

## 🛠️ Scripts y Automatización

### ⚙️ Script de Configuración (`scripts/setup.py`)
```bash
python scripts/setup.py
# ✅ Valida configuración
# ✅ Crea directorios
# ✅ Instala dependencias
# ✅ Verifica componentes
# ✅ Inicializa base de datos
```

### � Procesamiento PDF (`scripts/process_pdfs.py`)
```bash
# Procesar archivo individual
python scripts/process_pdfs.py process --file mi_pdf.pdf

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
cp ley_30364.pdf docs/raw_pdfs/
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

### ❌ "OPENAI_API_KEY no configurada"
```bash
# Editar .env
OPENAI_API_KEY=sk-...
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
- **API Docs** - `http://localhost:8000/docs` (Swagger)
- **DeepEval** - Documentación de evaluación
- **Docling** - Guía de procesamiento PDF

### 🔗 Enlaces Útiles
- **OpenAI API** - https://platform.openai.com/
- **LightRAG** - https://github.com/HKUDS/LightRAG
- **Pydantic AI** - https://pydantic-ai.github.io/
- **FastAPI** - https://fastapi.tiangolo.com/

---

## 🎯 Resumen de Cambios v2.0

### 🔄 Arquitectura Actualizada
- **Node.js → Python + FastAPI**
- **OpenAI simple → Docling + LightRAG + Pydantic AI**
- **Monolito básico → Monolito modular avanzado**

### 🚀 Nuevas Capacidades
- **Procesamiento inteligente de PDFs** con Docling
- **RAG con grafos de conocimiento** con LightRAG
- **Agentes validados** con Pydantic AI
- **Evaluación automática** con DeepEval
- **Scripts de automatización** completos

### 📈 Mejoras de Calidad
- **Respuestas estructuradas** sin alucinaciones
- **Validación automática** de cada respuesta
- **Testing continuo** de calidad del sistema
- **Monitoreo detallado** de métricas

---

**🎉 IA Jurídica v2.0: Sistema legal bilingüe con procesamiento inteligente de documentos y calidad garantizada.**
