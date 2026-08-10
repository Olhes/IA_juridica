# IA Jurídica v2.1

Asistente virtual bilingüe (quechua-español) especializado en derecho familiar y procesamiento inteligente de documentos legales para comunidades andinas y rurales de América Latina.

## 🚀 Inicio Rápido

### Requisitos
- Python 3.12
- UV (gestor de dependencias)
- Docker Desktop
- API Key de Cohere (obligatoria)

### Instalación

```bash
# Instalar UV según https://docs.astral.sh/uv/getting-started/installation/

# Clonar repositorio
cd IA_juridica

# Instalar dependencias
uv sync

# Configurar variables de entorno
# Editar backend/.env con tu COHERE_API_KEY
```

### Variables de Entorno

Crear `backend/.env`:

```env
COHERE_API_KEY=tu_api_key_aqui
ANONYMOUS_SESSION_SECRET=secreto_aleatorio_de_al_menos_32_bytes
DEBUG=true
DATABASE_HOST=localhost
DATABASE_PORT=5433
DATABASE_NAME=juridica_db
DATABASE_USER=juridica_user
DATABASE_PASSWORD=juridica_password

# Configuración de Grafo de Conocimiento
LOAD_LOCAL_KG=true  # Usar grafo local (recomendado para desarrollo)
NEO4J_ENABLED=false  # Neo4j Aura (opcional, requiere configuración adicional)
# NEO4J_URI=neo4j+s://tu-instancia-aura.databases.neo4j.io
# NEO4J_USER=tu_usuario
# NEO4J_PASSWORD=tu_password
# NEO4J_DATABASE=tu_database
```

### Start Development

```bash
# Starts PostgreSQL and Redis, waits for both health checks, then starts backend and frontend.
pnpm run dev:full
```

Use this single command after completing the dependency and environment setup above. Ctrl+C stops the backend and frontend only; PostgreSQL and Redis remain available in Docker.

## 📡 Endpoints API

### Chat Persistente
- `POST /session/bootstrap` - Crear o renovar sesión anónima HttpOnly
- `POST /chat/message` - Enviar mensaje con persistencia
- `GET /chat/conversations` - Listar conversaciones del usuario
- `GET /chat/conversations/{id}` - Obtener historial completo
- `POST /chat/conversations` - Crear nueva conversación
- `PUT /chat/conversations/{id}` - Actualizar conversación
- `DELETE /chat/conversations/{id}` - Eliminar conversación
- `GET /chat/search?q=termino` - Buscar conversaciones
- `GET /chat/health` - Health check de chat (Redis + PostgreSQL)

### Consultas Legales
- `POST /legal-query` - Consulta legal con RAG y validación
- `POST /legal-query-stream` - Streaming NDJSON para chat en tiempo real
- `GET /health` - Health check del sistema

### Documentos
- `POST /upload-pdf` - Subir y procesar PDF (admin habilitado + `ADMIN_API_KEY`)
- `POST /batch-process` - Procesar todos los PDFs pendientes (requiere API Key)
- `GET /documents` - Listar documentos indexados
- `GET /knowledge-graph` - Obtener grafo de conocimiento

### Administración
- `POST /evaluate-system` - Ejecutar evaluación completa (requiere API Key)
- `POST /generate-pdf-report` - Generar informe PDF

## 🏗️ Arquitectura

### Backend (FastAPI)
- **RAG**: LightRAG con grafos de conocimiento (local o Neo4j Aura)
- **LLM**: Cohere (embeddings, reranking, generación)
- **Modelo**: command-r7b-12-2024
- **Traducción**: Google Translate API (español ↔ quechua)
- **Validación**: Pipeline anti-alucinación con Pydantic
- **Procesamiento PDF**: Docling para extracción estructurada
- **Prompt Templates**: Respuestas conversacionales estilo ChatGPT/Gemini

### Frontend (Next.js)
- Clean Architecture (domain/application/infrastructure/presentation)
- TypeScript + Tailwind CSS
- Streaming NDJSON para chat en tiempo real

### Base de Datos
- **PostgreSQL**: Chat persistente (Docker container en puerto 5433)
- **Redis**: Caché de sesiones (Docker container)
- **SQLite**: Consultas y estadísticas (desarrollo)
- **Grafo de Conocimiento**: LightRAG local (NetworkX) o Neo4j Aura (opcional)

### Visualización de Base de Datos

Para inspeccionar la base de datos PostgreSQL:

```bash
# Conectarse a la base de datos
docker exec -it juridica_postgres psql -U juridica_user -d juridica_db

# Ver todos los schemas
\dn

# Ver tablas del schema de conversaciones
\dt conversations_schema.*

# Ver estructura de una tabla específica
\d conversations_schema.conversations
\d conversations_schema.messages

# Ver datos de conversaciones
SELECT * FROM conversations_schema.conversations LIMIT 10;

# Ver mensajes de una conversación
SELECT * FROM conversations_schema.messages WHERE conversation_id = 'tu_conversation_id' ORDER BY created_at;

# Ver estadísticas
SELECT 
    c.id,
    c.title,
    COUNT(m.id) as message_count,
    MAX(m.created_at) as last_message
FROM conversations_schema.conversations c
LEFT JOIN conversations_schema.messages m ON c.id = m.conversation_id
GROUP BY c.id, c.title
ORDER BY last_message DESC NULLS LAST;
```

Para Redis:

```bash
# Conectarse a Redis
docker exec -it juridica_redis redis-cli

# Ver todas las claves (con prefijo)
KEYS conversation:*
KEYS session:*

# Ver contenido de una conversación cacheada
GET conversation:tu_conversation_id

# Ver información de sesión
GET session:tu_session_id

# Ver estadísticas de Redis
INFO memory
INFO clients
```

### Configuración del Grafo de Conocimiento

El sistema soporta dos modos de almacenamiento del grafo de conocimiento:

**1. Grafo Local (Recomendado para Desarrollo)**
```env
LOAD_LOCAL_KG=true
NEO4J_ENABLED=false
```
- Usa NetworkX para almacenamiento local
- Archivos en `backend/docs/knowledge_graph/`
- 18 documentos legales pre-procesados incluidos
- Más rápido y sin dependencias externas

**2. Neo4j Aura (Opcional para Producción)**
```env
LOAD_LOCAL_KG=false
NEO4J_ENABLED=true
NEO4J_URI=neo4j+s://tu-instancia-aura.databases.neo4j.io
NEO4J_USER=tu_usuario
NEO4J_PASSWORD=tu_password
NEO4J_DATABASE=tu_database
```
- Grafo de conocimiento en la nube
- Escalable para grandes volúmenes
- Requiere instancia de Neo4j Aura

### Estilo de Respuestas Conversacionales

El sistema utiliza prompt templates optimizados para respuestas naturales, similares a ChatGPT/Gemini:

- ✅ **Respuestas naturales** sin formatos rígidos
- ✅ **Tono empático y conversacional**
- ✅ **Adaptación a cada situación específica**
- ✅ **Integración fluida de información** en párrafos naturales
- ✅ **Sensibilidad cultural** para comunidades rurales

Los templates se encuentran en `backend/context/prompt_templates.py` y cubren:
- Violencia familiar (Ley 30364)
- Pensión de alimentos
- Derechos de identidad
- Consultas legales generales

## 📁 Estructura del Proyecto

```
ia-juridica/
├── backend/
│   ├── main.py                    # API principal
│   ├── agents/                    # Agentes legales (Cohere + Pydantic)
│   ├── rag/                       # LightRAG y grafo de conocimiento
│   ├── database/                  # PostgreSQL y Redis adapters
│   ├── config/                    # Settings y configuración
│   ├── docs/                      # Artefactos locales (dev)
│   │   ├── raw_pdfs/
│   │   ├── processed/
│   │   └── knowledge_graph/
│   └── Dockerfile
├── frontend/                      # Next.js + TypeScript
│   ├── app/                       # Rutas y API routes
│   └── src/                       # Clean Architecture
├── docker-compose.yml             # PostgreSQL + Redis
└── pyproject.toml                 # Dependencias Python
```

## 🔧 Solución de Problemas

### Grafo de Conocimiento

**Problema: Las respuestas son genéricas y no usan los documentos procesados**
- **Causa**: LightRAG no está inicializado correctamente o no está usando el grafo local
- **Solución**: Verificar que `LOAD_LOCAL_KG=true` en `backend/.env`
- **Verificación**: En los logs debería aparecer `"LegalRAG Engine inicializado en ./docs/knowledge_graph (18 documentos cargados del disco)"`

**Problema: El sistema intenta usar Neo4j pero falla**
- **Causa**: Configuración de Neo4j incorrecta o credenciales inválidas
- **Solución**: Cambiar a `LOAD_LOCAL_KG=true` y `NEO4J_ENABLED=false` para modo local

**Problema: Respuestas muy estructuradas con secciones fijas**
- **Causa**: Prompt templates configurados para formato estructurado
- **Solución**: Los templates ya están actualizados para estilo conversacional en `backend/context/prompt_templates.py`

### Chat Persistence Issues

**Problema: Las conversaciones desaparecen al reiniciar el frontend**
- **Causa**: El frontend no estaba cargando el conversation_id persistente
- **Solución**: El backend ahora guarda y recupera conversaciones automáticamente

**Problema: El bot responde pero no muestra contenido**
- **Causa**: Placeholder en `chat_service.py` línea 309
- **Solución**: Integración real con pipeline de IA implementada

**Problema: Mensajes no se guardan en la base de datos**
```bash
# Verificar conexión PostgreSQL
docker exec -it juridica_postgres psql -U juridica_user -d juridica_db

# Verificar schemas
\dn

# Verificar tablas
\dt conversations_schema.*

# Ver últimos mensajes
SELECT * FROM conversations_schema.messages ORDER BY created_at DESC LIMIT 5;
```

### PostgreSQL Connection Issues

Si tienes problemas conectando a PostgreSQL, revisa `POSTGRES_CONNECTION_ISSUES.md` para un análisis detallado de todos los errores encontrados y sus soluciones.

**Resumen rápido:**
- El container Docker PostgreSQL usa puerto **5433** (no 5432)
- Esto evita conflicto con PostgreSQL local en Windows
- Usuario: `juridica_user`, Contraseña: `juridica_password`
- Trust authentication habilitado para desarrollo

### Errores Comunes

**"COHERE_API_KEY no configurada"**
```bash
# Editar backend/.env
COHERE_API_KEY=tu_key_aqui
```

**"PostgreSQL connection failed"**
```bash
# Verificar containers Docker
docker ps

# Verificar puerto 5433
netstat -ano | findstr :5433

# Reiniciar containers
docker-compose down
docker-compose up -d
```

**"Redis connection failed"**
```bash
# Verificar Redis container
docker exec -it juridica_redis redis-cli ping

# Debería responder: PONG
```

## 📚 Documentación Adicional

- `docs/SECURITY.md` - Sesiones anónimas, despliegue, uploads y migración manual segura
- `API_DOC.md` - Documentación completa de la API
- `POSTGRES_CONNECTION_ISSUES.md` - Debugging de conexión PostgreSQL
- `DOCUMENTATION.md` - Documentación técnica detallada
- `CHANGELOG_MIGRACION_COHERE.md` - Historial de migración a Cohere

## 🎯 Temas Legales Soportados

- Violencia Familiar (Ley 30364)
- Pensión de Alimentos
- Medidas de Protección
- Régimen de Visitas y Tenencia
- Denuncias y Procesos Judiciales
- Filiación y Derecho a la Identidad

## 📞 Soporte

- **API Docs**: `http://localhost:8000/docs`
- **Health Check**: `http://localhost:8000/health`
- **Frontend**: `http://localhost:3000`

---

**Versión**: 2.1  
**Última actualización**: 2026-04-24
