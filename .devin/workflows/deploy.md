---
description: Pipeline completo de despliegue para IA Jurídica
---

# Pipeline de Despliegue - IA Jurídica

## Pre-requisitos
- Docker y Docker Compose instalados
- Cuenta de Cohere con API key
- Servidor con puertos 3000 (frontend) y 8000 (backend) disponibles
- Opcional: Servidor Neo4j para knowledge graph

## 1. Configuración de Variables de Entorno

### Crear archivo .env.production
```bash
cp env.production.example .env.production
```

### Editar .env.production con valores reales:
```env
# Required
COHERE_API_KEY=tu-api-key-de-cohere
SYSTEM_PROMPT=Eres un asistente legal peruano de derecho familiar...
SECRET_KEY=genera-una-clave-segura-larga-y-aleatoria

# Cohere model config
COHERE_EMBED_MODEL=embed-multilingual-v3.0
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
COHERE_LLM_MODEL=command-r7b-12-2024
COHERE_MAX_TOKENS=2048
COHERE_TEMPERATURE=0.3

# Backend runtime
DEBUG=false
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Security
ADMIN_API_KEY=genera-otra-clave-segura
RATE_LIMIT_PER_MINUTE=30

# CORS (ajustar a tu dominio)
CORS_ORIGINS=["https://tu-dominio.com"]

# Neo4j (opcional, si lo vas a usar)
NEO4J_ENABLED=true
NEO4J_URI=bolt://tu-servidor-neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=tu-contraseña-neo4j
NEO4J_DATABASE=neo4j
```

## 2. Despliegue de Infraestructura (Desarrollo)

Si necesitas base de datos y servicios vectoriales localmente:

```bash
docker-compose up -d
```

Esto inicia:
- PostgreSQL (puerto 5433)
- Redis (puerto 6379)
- Weaviate (puerto 8080)

## 3. Despliegue de Aplicación (Producción)

### Opción A: Docker Compose (Recomendado para VPS simple)

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

Esto construye e inicia:
- Backend (puerto 8000)
- Frontend (puerto 3000)

### Opción B: Construcción manual de imágenes

```bash
# Construir backend
docker build -f backend/Dockerfile -t ia-juridica-backend:latest .

# Construir frontend
docker build -f frontend/Dockerfile -t ia-juridica-frontend:latest .

# Ejecutar con docker-compose.prod.yml
docker-compose -f docker-compose.prod.yml up -d
```

## 4. Verificación del Despliegue

### Verificar backend
```bash
curl http://localhost:8000/health
```

### Verificar frontend
```bash
curl http://localhost:3000
```

### Ver logs
```bash
# Logs backend
docker logs ia-juridica-backend

# Logs frontend
docker logs ia-juridica-frontend
```

## 5. Configuración de Proxy/Reverse Proxy (Nginx)

### Ejemplo de configuración Nginx
```nginx
server {
    listen 80;
    server_name tu-dominio.com;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 6. SSL con Let's Encrypt (Recomendado)

```bash
# Instalar certbot
sudo apt install certbot python3-certbot-nginx

# Obtener certificado
sudo certbot --nginx -d tu-dominio.com
```

## 7. Monitoreo y Mantenimiento

### Ver estado de contenedores
```bash
docker-compose -f docker-compose.prod.yml ps
```

### Reiniciar servicios
```bash
docker-compose -f docker-compose.prod.yml restart
```

### Actualizar aplicación
```bash
# Pull cambios
git pull

# Reconstruir y reiniciar
docker-compose -f docker-compose.prod.yml up -d --build
```

### Ver logs en tiempo real
```bash
docker-compose -f docker-compose.prod.yml logs -f
```

## 8. Troubleshooting Común

### Backend no inicia
- Verificar que .env.production exista
- Verificar API keys de Cohere
- Revisar logs: `docker logs ia-juridica-backend`

### Frontend no conecta con backend
- Verificar CORS_ORIGINS en .env.production
- Verificar que backend esté healthy: `docker ps`

### Error de conexión a base de datos
- Si usas infraestructura externa, configurar variables de DB en .env.production
- Verificar que postgres/redis/weaviate estén accesibles

## 9. Escalado (Opcional)

Para múltiples workers del backend:

```bash
# En docker-compose.prod.yml, modificar CMD en Dockerfile o usar:
docker-compose -f docker-compose.prod.yml up -d --scale backend=3
```

## 10. Backup

### Backup de volúmenes
```bash
# Backup de docs
docker run --rm -v ia_juridica_backend_docs:/data -v $(pwd):/backup alpine tar czf /backup/docs_backup.tar.gz /data

# Backup de logs
docker run --rm -v ia_juridica_backend_logs:/data -v $(pwd):/backup alpine tar czf /backup/logs_backup.tar.gz /data
```
