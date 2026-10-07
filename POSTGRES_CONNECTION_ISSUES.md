# Problemas de conexión con PostgreSQL: registro de depuración

## Resumen
Este documento registra los problemas encontrados al conectar el backend con PostgreSQL y la forma en que se resolvieron.

## Análisis de causas raíz

### Problema principal: conflicto de puertos
El problema principal era que **PostgreSQL 17 estaba instalado localmente en Windows** y escuchaba en el puerto 5432, por lo que interceptaba los intentos de conexión destinados al contenedor de Docker.

## Problemas y soluciones detallados

### 1. Archivos heredados del adaptador de PostgreSQL
**Problema:** Existían varios archivos adaptadores de PostgreSQL (`postgres_adapter.py`, `postgres_adapter_old.py`, etc.), lo que generaba dudas sobre cuál se estaba usando.

**Solución:** Se eliminaron los archivos heredados y se conservó únicamente `postgres_adapter_final.py`.

### 2. NameError en settings.py
**Problema:** `DATABASE_URL` y `SQLALCHEMY_DATABASE_URL` hacían referencia a `DATABASE_USER`, `DATABASE_PASSWORD`, etc., antes de que se definieran en la clase.

**Error:**
```
NameError: name 'DATABASE_USER' is not defined
```

**Solución:** Se reordenaron las declaraciones en `settings.py` para definir todas las variables `DATABASE_*` antes de utilizarlas al construir la URL.

### 3. Credenciales codificadas en el adaptador
**Problema:** `postgres_adapter_final.py` utilizaba credenciales codificadas en el archivo en lugar de cargarlas desde la configuración.

**Solución:** Se actualizó el adaptador para usar `settings.DATABASE_USER` y `settings.DATABASE_PASSWORD`.

### 4. Variables de entorno no cargadas
**Problema:** El archivo `.env` no se leía correctamente o los valores predeterminados de `settings.py` eran incorrectos.

**Solución:** Se verificó que `pydantic-settings` estuviera configurado correctamente con `env_file=".env"` y se corrigieron los valores predeterminados.

### 5. Incompatibilidad entre usuario y base de datos
**Problema:** El backend intentaba conectarse a la base de datos `ia_juridica`, pero el contenedor de Docker creaba `juridica_db`.

**Solución:** Se cambió `DATABASE_NAME` en `settings.py` de `ia_juridica` a `juridica_db` para que coincidiera con la configuración de Docker Compose.

### 6. Usuario no creado en PostgreSQL
**Problema:** El usuario `juridica_user` no existía en la instancia de PostgreSQL.

**Solución:** Se creó el usuario y se le otorgaron permisos:
```sql
CREATE USER juridica_user WITH PASSWORD 'juridica_password';
GRANT ALL PRIVILEGES ON DATABASE juridica_db TO juridica_user;
```

### 7. Contraseña predeterminada incorrecta
**Problema:** El valor predeterminado de `DATABASE_PASSWORD` en `settings.py` era una cadena vacía.

**Solución:** Se cambió el valor predeterminado de `""` a `"juridica_password"`.

### 8. Configuración de POSTGRES_HOST_AUTH_METHOD
**Problema:** El archivo Docker Compose tenía `POSTGRES_HOST_AUTH_METHOD: trust`, que omitía la autenticación por contraseña dentro del contenedor, pero causaba problemas en conexiones externas.

**Solución:** Primero se eliminó para exigir autenticación por contraseña; después se volvió a añadir junto con `POSTGRES_INITDB_ARGS: "--auth-host=trust"` para desarrollo.

### 9. Configuración de pg_hba.conf
**Problema:** El archivo `pg_hba.conf` dentro del contenedor estaba configurado así:
- `host all all 127.0.0.1/32 trust` (for localhost inside container)
- `host all all all scram-sha-256` (for external connections requiring password)

Esto hacía que las conexiones externas requirieran contraseña, aunque el backend se conectaba desde fuera del contenedor.

**Solución:** Se añadió `host all all 0.0.0.0/0 md5` para permitir conexiones externas con autenticación md5; luego, para desarrollo, se cambió a `host all all all trust`.

### 10. Persistencia del volumen de Docker
**Problema:** El volumen de Docker conservaba la configuración anterior de `pg_hba.conf` incluso después de modificar el archivo Docker Compose.

**Solución:** Se eliminó el volumen con `docker-compose down -v` y se volvió a crear.

### 11. Varios archivos Docker Compose
**Problema:** Existían varios archivos `docker-compose` (`docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.simple.yml`), lo que generaba dudas sobre cuál se estaba usando.

**Solución:** Se eliminaron los archivos no utilizados y se conservó únicamente `docker-compose.yml`.

### 12. Conflicto con el servicio local de PostgreSQL
**Problema:** PostgreSQL 17 estaba instalado localmente en Windows y escuchaba en el puerto 5432, por lo que interceptaba todos los intentos de conexión.

**Evidencia:**
```
netstat -ano | findstr :5432
TCP    0.0.0.0:5432           0.0.0.0:0              LISTENING       3468
TCP    0.0.0.0:5432           0.0.0.0:0              LISTENING       8756
```

Dos procesos escuchaban en el puerto 5432 (PID 3468 y 8756).

**Solución:** Se configuró el contenedor de Docker para usar el puerto 5433 en lugar del 5432:
```yaml
ports:
  - "5433:5432"
```

También se actualizó el adaptador para usar el puerto 5433:
```python
conn = psycopg.connect(
    host=settings.DATABASE_HOST or "localhost",
    port=5433,  # Puerto del container Docker (evita conflicto con PostgreSQL local)
    dbname=settings.DATABASE_NAME or "juridica_db",
    user=actual_user,
    password="",
    connect_timeout=10
)
```

### 13. Anulación mediante variable de entorno
**Problema:** El archivo `.env` anulaba la configuración del puerto en `settings.py`, por lo que el adaptador seguía intentando conectarse al puerto 5432.

**Solución:** Se fijó el puerto 5433 en el adaptador para evitar la anulación de `.env`.

## Configuración final

### Docker Compose (docker-compose.yml)
```yaml
services:
  postgres:
    image: postgres:15-alpine
    container_name: ia_juridica_postgres
    environment:
      POSTGRES_DB: juridica_db
      POSTGRES_USER: juridica_user
      POSTGRES_PASSWORD: juridica_password
      POSTGRES_HOST_AUTH_METHOD: trust
      POSTGRES_INITDB_ARGS: "--auth-host=trust"
    ports:
      - "5433:5432"  # Cambiado de 5432 para evitar conflictos con PostgreSQL local
```

### Settings (backend/config/settings.py)
```python
DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", "5433"))  # Cambiado a 5433
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "juridica_db")
DATABASE_USER: str = os.getenv("DATABASE_USER", "postgres")
DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "")
```

### Adapter (backend/database/postgres_adapter_final.py)
```python
def connect_sync():
    actual_user = "juridica_user"
    
    try:
        conn = psycopg.connect(
            host=settings.DATABASE_HOST or "localhost",
            port=5433,  # Fijado para evitar que .env lo anule
            dbname=settings.DATABASE_NAME or "juridica_db",
            user=actual_user,
            password="",  # Autenticación de confianza
            connect_timeout=10
        )
        return conn
```

## Lecciones aprendidas

1. **Verificar siempre los conflictos de puertos** al usar contenedores Docker en Windows. Los servicios locales pueden interceptar los puertos del contenedor.
2. **Las variables de entorno pueden anular los valores predeterminados** de formas inesperadas. Fijar temporalmente valores críticos durante la depuración puede ayudar a aislar problemas.
3. **Los volúmenes de Docker conservan la configuración** incluso después de cambiar los archivos Compose. Usar `docker-compose down -v` para restablecerlos.
4. **pg_hba.conf es fundamental** para la autenticación de PostgreSQL. Comprender sus reglas es esencial para depurar problemas de conexión.
5. **La autenticación de confianza es práctica para desarrollo**, pero en producción debe sustituirse por una autenticación adecuada.

## Verificación

Para verificar que la conexión funciona:
```bash
# Comprobar que solo el contenedor de Docker escucha en el puerto 5433
netstat -ano | findstr :5433

# Comprobar que el backend se conecta correctamente
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Salida esperada:
```
🔍 Conectando a PostgreSQL (intento 1/3)...
  🔧 Usando usuario: juridica_user (trust auth)
  ✅ Conexión exitosa para: juridica_user
✅ PostgreSQL conectado: PostgreSQL...
✅ Conexión PostgreSQL inicializada
```
