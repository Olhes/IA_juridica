# 🚀 Guía de Configuración Rápida - IA Jurídica v2.0

## 📋 Requisitos Previos

- **Python 3.9+**
- **API Key de OpenAI** (obligatoria)
- **PDFs legales** (opcional para empezar)

## ⚡ Configuración Automática (Recomendado)

### 1. Ejecutar Script de Configuración

```bash
cd ia-juridica/backend
python scripts/setup.py
```

El script configurará automáticamente:
- ✅ Validará la configuración
- ✅ Creará todos los directorios necesarios
- ✅ Instalará dependencias
- ✅ Verificará componentes
- ✅ Inicializará la base de datos
- ✅ Configurará variables de entorno

### 2. Configurar API Keys

Edita el archivo `.env` creado:

```env
# OpenAI (OBLIGATORIO)
OPENAI_API_KEY=tu_api_key_de_openai_aqui

# Seguridad
SECRET_KEY=tu_secreto_unico_aqui

# Otros (opcionales para empezar)
DEBUG=true
LOG_LEVEL=INFO
```

### 3. Iniciar el Servidor

```bash
python main.py
```

El servidor iniciará en: `http://localhost:8000`

### 4. Frontend (Next.js)

```bash
cd ../frontend
npm install
npm run dev
```

Frontend disponible en: `http://localhost:3000`

### 4.1 Levantar backend + frontend con un solo comando

Desde la raíz del proyecto:

```bash
npm install
npm run install-frontend
npm run dev
```

- `npm run dev` levanta ambos servicios en paralelo (`backend` y `frontend`).
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

Si tu backend FastAPI corre en otra URL/puerto, define:

```bash
# en frontend/.env.local
FASTAPI_BASE_URL=http://127.0.0.1:8000
```

### 5. Sobre `npm install` en raíz vs `frontend/`

- `npm install` en `frontend/` instala dependencias reales de la UI (Next.js, React, Tailwind).
- `npm install` en la raíz solo aplica si usas scripts del `package.json` raíz; no instala librerías del frontend.
- Con la configuración actual, para trabajar solo en frontend basta con instalar una sola vez dentro de `frontend/`.

## 📁 Subir y Procesar PDFs

> Recomendación: en producción usa **modo cloud** para no versionar PDFs en Git.

### Modo Local (desarrollo)

### Método 1: API REST

```bash
# Subir un PDF
curl -X POST "http://localhost:8000/upload-pdf" \
  -F "file=@mi_documento_legal.pdf"

# Procesar todos los PDFs
curl -X POST "http://localhost:8000/batch-process"
```

### Método 2: Línea de Comandos

```bash
# Procesar un archivo específico
python scripts/process_pdfs.py process --file mi_documento.pdf

# Procesar todo el directorio
python scripts/process_pdfs.py process-dir

# Ver estadísticas
python scripts/process_pdfs.py stats
```

### Método 3: Copiar Directamente

```bash
# Copiar PDFs al directorio de procesamiento
cp tus_pdfs/*.pdf docs/raw_pdfs/

# Luego ejecutar procesamiento batch
python scripts/process_pdfs.py process-dir
```

### Modo Cloud (recomendado para producción)

1. Frontend solicita URL firmada a FastAPI.
2. Frontend sube el PDF directo a object storage (S3/GCS/R2).
3. FastAPI/Storage encola el documento para procesamiento.
4. Worker Python procesa con Docling + LightRAG.
5. Frontend consulta estado (`uploaded`, `processing`, `processed`, `failed`).

Referencia de implementación: `CLOUD_PDF_PIPELINE.md`.

### Evitar subir PDFs al repositorio

- El proyecto ya ignora `backend/docs/raw_pdfs`, `backend/docs/processed`, `backend/docs/knowledge_graph` y `backend/docs/failed` en `.gitignore`.
- Si ya tienes PDFs versionados, retíralos del índice de Git con `git rm --cached` y mantén solo `.gitkeep`.

## 🎯 Estructura de Directorios

```
ia-juridica/
├── backend/
│   ├── main.py            # 🚀 Servidor principal
│   ├── docs/              # 📄 Artefactos locales (dev)
│   │   ├── raw_pdfs/
│   │   ├── processed/
│   │   ├── knowledge_graph/
│   │   └── failed/
│   ├── scripts/           # 🛠️ Scripts utilitarios
│   └── config/            # ⚙️ Configuración
├── frontend/              # 🎨 Next.js + TypeScript
│   ├── app/
│   └── src/
└── requirements.txt       # 📦 Dependencias
```

## 📚 Tipos de PDFs Recomendados

### ✅ PDFs Ideales para Docling

- **Códigos legales** (Código Civil, Penal)
- **Leyes específicas** (Ley 30364, etc.)
- **Reglamentos** y **directivas**
- **Formatos judiciales** (demandas, denuncias)
- **Jurisprudencia** y **sentencias**
- **Documentos gubernamentales**

### 📋 Ejemplos por Tema

**Violencia Familiar:**
- Ley 30364 (completa)
- Reglamento de la Ley 30364
- Formatos de denuncia
- Guías del Ministerio de la Mujer

**Pensión de Alimentos:**
- Código Civil (artículos 472-485)
- Código Procesal Civil
- Tablas de pensiones
- Modelos de demanda

**Medidas de Protección:**
- Protocolos de atención
- Formatos de solicitud
- Guías policiales
- Directivas judiciales

## 🔍 Verificar Procesamiento

### 1. Revisar Archivos Procesados

```bash
# Ver markdown generados
ls docs/processed/

# Revisar contenido de un archivo
cat docs/processed/mi_documento.md
```

### 2. Validar Calidad

```bash
# Ejecutar validación
python scripts/process_pdfs.py validate

# Ver estadísticas completas
python scripts/process_pdfs.py stats --verbose
```

### 3. Probar API

```bash
# Consulta legal de prueba
curl -X POST "http://localhost:8000/legal-query" \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Qué hago si mi pareja me golpea?", "language": "spanish"}'
```

## 🛠️ Solución de Problemas

### ❌ Error: "OPENAI_API_KEY no configurada"

**Solución:**
```bash
# Editar .env
nano .env
# Agregar: OPENAI_API_KEY=tu_key_aqui
```

### ❌ Error: "Docling no disponible"

**Solución:**
```bash
# Reinstalar dependencias
pip install -r requirements.txt --force-reinstall
```

### ❌ Error: "Directorio no existe"

**Solución:**
```bash
# Ejecutar setup nuevamente
python scripts/setup.py
```

### ❌ Error: "PDF corrupto"

**Solución:**
```bash
# Mover a failed y reprocesar
python scripts/process_pdfs.py reprocess
```

## 📊 Monitoreo y Evaluación

### 1. Ver Sistema

```bash
# Health check
curl http://localhost:8000/health

# Ver documentos procesados
curl http://localhost:8000/documents
```

### 2. Evaluar Calidad

```bash
# Ejecutar evaluación automática
curl -X POST "http://localhost:8000/evaluate-system"
```

### 3. Ver Grafo de Conocimiento

```bash
# Obtener datos del grafo
curl http://localhost:8000/knowledge-graph
```

## 🎯 Próximos Pasos

### 1. Probar Consultas Legales

Una vez procesados los PDFs, prueba consultas como:
- "¿Qué hago si mi pareja me golpea?"
- "¿Cómo solicito pensión de alimentos?"
- "¿Qué son las medidas de protección?"

### 2. Personalizar Prompts

Edita los agentes en `backend/agents/pydantic_agents.py` para ajustar respuestas.

### 3. Agregar Más PDFs

Continúa agregando más documentos legales según necesites.

### 4. Configurar Producción

Para producción, ajusta:
- `DEBUG=false`
- `SECRET_KEY` seguro
- Rate limiting
- HTTPS

## 📞 Ayuda

- **Documentación completa**: `DOCUMENTATION.md`
- **Arquitectura cloud de PDFs**: `CLOUD_PDF_PIPELINE.md`
- **API docs**: `http://localhost:8000/docs`
- **Logs**: `logs/juridica.log`

---

**🎉 ¡Listo! Tu sistema IA Jurídica está configurado y procesando documentos legales.**
