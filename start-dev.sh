#!/bin/bash

echo "🚀 Iniciando IA Jurídica - Modo Desarrollo"
echo

# Verificar si Docker está corriendo
echo "🐋 Verificando Docker..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker no está corriendo. Por favor inícialo primero."
    exit 1
fi

# Iniciar Weaviate
echo "📊 Iniciando Weaviate..."
docker run -d --name weaviate -p 8080:8080 -p 8081:8081 -e QUERY_DEFAULTS_LIMIT=25 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true -e PERSISTENCE_DATA_PATH=/var/lib/weaviate -v ./data:/var/lib/weaviate semitechnologies/weaviate:1.19.0

# Esperar a que Weaviate esté listo
echo "⏳ Esperando a Weaviate esté listo..."
while ! curl -f http://localhost:8080/v1/.well-known/ready > /dev/null 2>&1; do
    sleep 3
done
echo "✅ Weaviate listo"

# Iniciar el backend
echo "🤖 Iniciando backend de IA Jurídica..."
cd backend

# Configurar variables de entorno
export COHERE_API_KEY=""
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5432"
export POSTGRES_DB="ia_juridica"
export POSTGRES_USER="postgres"
export POSTGRES_PASSWORD="postgres"
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export VECTOR_DB_HOST="localhost"
export VECTOR_DB_PORT="8080"
export HF_HOME="D:/huggingface_cache"

# Instalar dependencias
echo "📦 Instalando dependencias de Python..."
cd backend
if [ ! -d "venv" ]; then
    python -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# Iniciar servidor
echo "🌐 Iniciando servidor FastAPI..."
python main.py
