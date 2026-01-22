# IA Jurídica - Documentación Técnica

## 🎯 Descripción del Proyecto

Asistente virtual bilingüe (quechua-español) especializado en consultas de derecho digital para comunidades andinas y rurales de América Latina.

## 🏗️ Arquitectura Técnica

### Monolito Modular
- **Backend**: Node.js + Express con servicios modulares
- **Frontend**: React SPA con Tailwind CSS
- **IA**: OpenAI API (GPT-4)
- **Base de Datos**: SQLite
- **PDF**: PDFKit

### Estructura del Proyecto

```
ia-juridica/
├── backend/                  # API REST y servicios
│   ├── controllers/          # Manejo de rutas HTTP
│   ├── models/              # Modelos de datos
│   ├── services/            # Lógica de negocio modular
│   │   ├── contracts/       # Contratos de servicios
│   │   ├── openai/          # Integración OpenAI
│   │   ├── 
│   │   ├── legal/  translation/     # Manejo bilingüe         # Procesamiento legal
│   │   └── pdf/          # Generación i   nformes
│   ├── middleware/          # Validación y seguridad
│   ├── routes/              # Endpoints API
│   ├── utils/               # Funciones helper
│   └── database/            # Base de datos SQLite
├── frontend/                 # React SPA
│   ├── src/components/      # Componentes UI
│   └── public/              # Assets estáticos
├── config/                   # Configuración
└── docs/                     # Documentación
```

## 📋 Requisitos

### Backend
- Node.js 16+
- npm o yarn
- API Key de OpenAI

### Frontend
- Node.js 16+
- npm o yarn

## 🛠️ Instalación

1. **Instalar dependencias**
```bash
npm run install-deps
```

2. **Configurar variables de entorno**
```bash
cd backend
cp .env.example .env
# Editar .env con tu API Key de OpenAI
```

3. **Iniciar desarrollo**
```bash
npm run dev
```

## 📡 Endpoints API

### Consultas Legales
- `POST /api/legal/consult` - Procesa consulta legal
- `POST /api/legal/pdf` - Genera informe PDF
- `POST /api/legal/validate` - Valida consulta
- `GET /api/legal/health` - Estado del servicio

### Idioma
- `POST /api/language/detect` - Detecta idioma del texto

## 🔧 Variables de Entorno

```env
# Server
PORT=5000
NODE_ENV=development

# OpenAI
OPENAI_API_KEY=tu_api_key_aqui
OPENAI_MODEL=gpt-4

# Database
DB_PATH=./database/juridica.db

# Security
JWT_SECRET=tu_secreto_aqui
RATE_LIMIT_WINDOW_MS=900000
RATE_LIMIT_MAX_REQUESTS=100
```

## 🧠 Servicios Core

### LegalService
Procesamiento principal de consultas con validación y contexto bilingüe.

### OpenAIService
Integración con API de OpenAI para procesamiento de lenguaje natural.

### TranslationService
Manejo de traducción entre quechua y español con cache.

### PDFService
Generación de informes legales personalizados.

## 📊 Base de Datos

### Tablas Principales
- `legal_queries` - Consultas procesadas
- `daily_stats` - Estadísticas diarias
- `popular_topics` - Temas populares
- `error_logs` - Registro de errores

## 🔒 Seguridad

- Rate limiting por IP
- Validación de entrada sanitizada
- Headers de seguridad
- Logging de eventos

## 🌐 Despliegue

### Backend (Railway/Heroku)
```bash
npm run build
npm start
```

### Frontend (Vercel/Netlify)
```bash
cd frontend
npm run build
```

## 📝 Notas sobre Tailwind CSS

Los warnings de `@tailwind` son normales durante desarrollo. Se resuelven al:
1. Instalar dependencias: `npm install`
2. Iniciar servidor de desarrollo: `npm start`

Las reglas `@tailwind` son procesadas por PostCSS durante el build.
