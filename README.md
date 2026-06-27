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
# Instalar UV
pip install uv

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
SECRET_KEY=tu_secreto_unico
DEBUG=true
DATABASE_HOST=localhost
DATABASE_PORT=5433
DATABASE_NAME=juridica_db
DATABASE_USER=juridica_user
DATABASE_PASSWORD=juridica_password
```

### Iniciar Servicios

```bash
# Iniciar Docker (PostgreSQL + Redis)
docker-compose up -d

# Iniciar backend
cd backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Iniciar frontend (opcional)
cd frontend
npm install
npm run dev
```

## 📡 Endpoints API

### Chat Persistente
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
- `POST /upload-pdf` - Subir y procesar PDF (requiere API Key)
- `POST /batch-process` - Procesar todos los PDFs pendientes (requiere API Key)
- `GET /documents` - Listar documentos indexados
- `GET /knowledge-graph` - Obtener grafo de conocimiento

### Administración
- `POST /evaluate-system` - Ejecutar evaluación completa (requiere API Key)
- `POST /generate-pdf-report` - Generar informe PDF

## 🏗️ Arquitectura

### Backend (FastAPI)
- **RAG**: LightRAG con grafos de conocimiento
- **LLM**: Cohere (embeddings, reranking, generación)
- **Traducción**: Google Translate API (español ↔ quechua)
- **Validación**: Pipeline anti-alucinación con Pydantic
- **Procesamiento PDF**: Docling para extracción estructurada

### Frontend (Next.js)
- Clean Architecture (domain/application/infrastructure/presentation)
- TypeScript + Tailwind CSS
- Streaming NDJSON para chat en tiempo real

### Base de Datos
- **PostgreSQL**: Chat persistente (Docker container en puerto 5433)
- **Redis**: Caché de sesiones (Docker container)
- **SQLite**: Consultas y estadísticas (desarrollo)

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
