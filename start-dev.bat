@echo off
echo 🚀 Iniciando IA Jurídica - Modo Desarrollo
echo.

REM Verificar si Docker Desktop está corriendo
echo "🐋 Verificando Docker Desktop..."
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Desktop no está corriendo. Por favor inícialo primero.
    pause
    exit /b 1
)

REM Iniciar Weaviate
echo "📊 Iniciando Weaviate..."
docker run -d --name weaviate -p 8080:8080 -p 8081:8081 -e QUERY_DEFAULTS_LIMIT=25 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true -e PERSISTENCE_DATA_PATH=/var/lib/weaviate -v ./data:/var/lib/weaviate semitechnologies/weaviate:1.19.0

REM Esperar a que Weaviate esté listo
:weaviate_check
echo "⏳ Esperando a Weaviate esté listo..."
timeout /t 3 /nobreak
curl -f http://localhost:8080/v1/.well-known/ready >nul 2>&1
if %errorlevel% neq 0 (
    goto weaviate_check
)
echo ✅ Weaviate listo

REM Iniciar el backend
echo 🤖 Iniciando backend de IA Jurídica...
cd backend

REM Configurar variables de entorno
set COHERE_API_KEY=
set POSTGRES_HOST=localhost
set POSTGRES_PORT=5432
set POSTGRES_DB=ia_juridica
set POSTGRES_USER=postgres
set POSTGRES_PASSWORD=postgres
set REDIS_HOST=localhost
set REDIS_PORT=6379
set VECTOR_DB_HOST=localhost
set VECTOR_DB_PORT=8080
set HF_HOME=D:/huggingface_cache

REM Instalar dependencias
echo 📦 Instalando dependencias de Python...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate
pip install -r requirements.txt

REM Iniciar servidor
echo 🌐 Iniciando servidor FastAPI...
python main.py

pause
