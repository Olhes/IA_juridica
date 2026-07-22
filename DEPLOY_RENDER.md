# Guía de部署 en Render

## Requisitos Previos

1. Cuenta en [Render](https://render.com)
2. Repositorio en GitHub con el código del proyecto
3. Servicios externos configurados:
   - **PostgreSQL**: Render PostgreSQL o servicio externo
   - **Redis**: Render Redis o servicio externo
   - **Neo4j Aura**: Ya configurado
   - **Qdrant**: Render o servicio externo (opcional, puede usar local)

## Pasos de Despliegue

### 1. Preparar Repositorio

```bash
# Asegurarse de que el código está en GitHub
git add .
git commit -m "Preparar para despliegue en Render"
git push origin main
```

### 2. Configurar Servicios Externos

#### PostgreSQL (Render)
1. En Render, crear nuevo servicio: **PostgreSQL**
2. Plan: Free (suficiente para desarrollo)
3. Guardar las credenciales:
   - Internal Database URL
   - Database Name
   - User
   - Password

#### Redis (Render)
1. En Render, crear nuevo servicio: **Redis**
2. Plan: Free
3. Guardar la Internal Redis URL

#### Qdrant (Opcional)
- Usar Qdrant Cloud o servicio externo
- O desplegar como servicio en Render (requiere Dockerfile adicional)

### 3. Crear Web Service en Render

1. En Render, crear nuevo servicio: **Web Service**
2. Conectar al repositorio de GitHub
3. Configurar:
   - **Name**: ia-juridica-backend
   - **Region**: Oregon (o la más cercana)
   - **Branch**: main
   - **Runtime**: Docker
   - **Dockerfile Path**: `./backend/Dockerfile.production`
   - **Context**: `.`
   - **Plan**: Free

### 4. Configurar Variables de Entorno

En el web service de Render, agregar las siguientes variables:

#### Variables Obligatorias
```env
PORT=8000
WORKERS=1
ENVIRONMENT=production
DEBUG=false
NEO4J_ENABLED=true
```

#### Credenciales de APIs
```env
COHERE_API_KEY=tu_api_key_cohere
SECRET_KEY=generar_aleatorio_32_caracteres
ANONYMOUS_SESSION_SECRET=generar_aleatorio_32_caracteres
```

#### Base de Datos
```env
DATABASE_URL=postgresql://usuario:password@host:puerto/nombre_db
```
(Usar la Internal Database URL de Render PostgreSQL)

#### Redis
```env
REDIS_URL=redis://usuario:password@host:puerto
```
(Usar la Internal Redis URL de Render Redis)

#### Neo4j Aura
```env
NEO4J_URI=neo4j+s://c3f1fd14.databases.neo4j.io
NEO4J_USER=c3f1fd14
NEO4J_PASSWORD=tu_password_aura
NEO4J_DATABASE=c3f1fd14
```

#### Qdrant (Opcional)
```env
QDRANT_URL=http://tu-qdrant-host:6333
```

### 5. Ajustar Dockerfile para Render

El `Dockerfile.production` ya está configurado para Render con:
- Health check en puerto 8000
- Variables PORT y WORKERS inyectadas
- Usuario no-root para seguridad
- Optimización de capas para builds rápidos

### 6. Desplegar

1. Click en **"Create Web Service"**
2. Render iniciará el build automático
3. Monitorear el build en la pestaña "Events"
4. Esperar a que el servicio esté "Live"

### 7. Verificar Despliegue

```bash
# Obtener la URL del servicio (ej: https://ia-juridica-backend.onrender.com)
curl https://tu-url.onrender.com/health
```

Debería retornar:
```json
{
  "status": "ready",
  "timestamp": "...",
  "services": {
    "cohere": "connected",
    "lightrag": "initialized",
    ...
  }
}
```

### 8. Configurar Dominio Personalizado (Opcional)

1. En el web service, ir a "Settings" → "Custom Domains"
2. Agregar dominio propio
3. Configurar DNS según instrucciones de Render

## Solución de Problemas

### Build Fallido
- Verificar logs en la pestaña "Events"
- Asegurar que `Dockerfile.production` existe en la ruta correcta
- Verificar que `pyproject.toml` y `uv.lock` están en el root

### Error de Conexión a Base de Datos
- Verificar que `DATABASE_URL` es correcta
- Asegurar que PostgreSQL está corriendo
- Verificar reglas de firewall de Render

### Error de Memoria (Free Tier)
- Reducir `WORKERS` a 1
- Limitar tamaño de knowledge graph
- Considerar upgrade a plan pago si es necesario

### Variables de Entorno No Cargadas
- Verificar que no hay espacios en blanco en los valores
- Usar comillas para valores con caracteres especiales
- Reiniciar el servicio después de cambiar variables

## Monitoreo

Render proporciona:
- **Logs**: Ver logs en tiempo real
- **Metrics**: CPU, memoria, respuesta
- **Alerts**: Configurar alertas de uptime
- **Deployments**: Historial de despliegues

## Costos Estimados (Free Tier)

- **Web Service**: Gratis (512 MB RAM, 0.1 CPU)
- **PostgreSQL**: Gratis (90 días, luego $7/mes)
- **Redis**: Gratis (25 MB, luego $5/mes)
- **Neo4j Aura**: Gratis (hasta cierto límite)

Total estimado: $0 - $12/mes después del período gratuito

## Escalado

Para producción:
- Upgrade plan de Web Service (Standard/Pro)
- Aumentar `WORKERS` en variables de entorno
- Configurar balanceador de carga
- Usar CDN para assets estáticos
