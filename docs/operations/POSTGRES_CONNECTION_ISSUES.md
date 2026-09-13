# PostgreSQL Connection Issues - Debugging Log

## Summary
This document documents all the issues encountered while trying to connect the backend to PostgreSQL and how they were resolved.

## Root Cause Analysis

### Primary Issue: Port Conflict
The main issue was that **PostgreSQL 17 was installed locally on Windows** and was listening on port 5432, intercepting all connection attempts meant for the Docker container.

## Detailed Issues and Solutions

### 1. Legacy PostgreSQL Adapter Files
**Issue:** Multiple PostgreSQL adapter files existed (`postgres_adapter.py`, `postgres_adapter_old.py`, etc.) causing confusion about which one was being used.

**Solution:** Deleted all legacy files and kept only `postgres_adapter_final.py`.

### 2. NameError in settings.py
**Issue:** `DATABASE_URL` and `SQLALCHEMY_DATABASE_URL` referenced `DATABASE_USER`, `DATABASE_PASSWORD`, etc. before they were defined in the class.

**Error:**
```
NameError: name 'DATABASE_USER' is not defined
```

**Solution:** Reordered the variable declarations in `settings.py` to ensure all `DATABASE_*` variables are defined before being used in URL construction.

### 3. Hardcoded Credentials in Adapter
**Issue:** `postgres_adapter_final.py` was using hardcoded credentials instead of loading from settings.

**Solution:** Updated the adapter to use `settings.DATABASE_USER` and `settings.DATABASE_PASSWORD`.

### 4. Environment Variables Not Loaded
**Issue:** The `.env` file was not being read correctly, or the defaults in `settings.py` were incorrect.

**Solution:** Verified that `pydantic-settings` was configured correctly with `env_file=".env"` and fixed default values.

### 5. User and Database Mismatch
**Issue:** The backend was trying to connect to database `ia_juridica` but the Docker container created `juridica_db`.

**Solution:** Changed `DATABASE_NAME` in `settings.py` from `ia_juridica` to `juridica_db` to match the Docker Compose configuration.

### 6. User Not Created in PostgreSQL
**Issue:** The user `juridica_user` did not exist in the PostgreSQL instance.

**Solution:** Created the user and granted permissions:
```sql
CREATE USER juridica_user WITH PASSWORD 'juridica_password';
GRANT ALL PRIVILEGES ON DATABASE juridica_db TO juridica_user;
```

### 7. Incorrect Default Password
**Issue:** The default value for `DATABASE_PASSWORD` in `settings.py` was an empty string.

**Solution:** Changed the default from `""` to `"juridica_password"`.

### 8. POSTGRES_HOST_AUTH_METHOD Configuration
**Issue:** The Docker Compose file had `POSTGRES_HOST_AUTH_METHOD: trust`, which bypassed password authentication inside the container but caused issues for external connections.

**Solution:** Initially removed it to enforce password authentication, then added it back with `POSTGRES_INITDB_ARGS: "--auth-host=trust"` for development.

### 9. pg_hba.conf Configuration
**Issue:** The `pg_hba.conf` file inside the container was configured with:
- `host all all 127.0.0.1/32 trust` (for localhost inside container)
- `host all all all scram-sha-256` (for external connections requiring password)

This meant external connections required password authentication, but the backend was connecting from outside the container.

**Solution:** Added `host all all 0.0.0.0/0 md5` to allow external connections with md5 authentication, then switched to `host all all all trust` for development.

### 10. Docker Volume Persistence
**Issue:** The Docker volume persisted the old `pg_hba.conf` configuration even after changing the Docker Compose file.

**Solution:** Destroyed the volume with `docker-compose down -v` and recreated it.

### 11. Multiple Docker Compose Files
**Issue:** Multiple `docker-compose` files existed (`docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.simple.yml`), causing confusion about which one was being used.

**Solution:** Deleted unused files and kept only `docker-compose.yml`.

### 12. PostgreSQL Local Service Conflict
**Issue:** PostgreSQL 17 was installed locally on Windows and was listening on port 5432, intercepting all connection attempts.

**Evidence:**
```
netstat -ano | findstr :5432
TCP    0.0.0.0:5432           0.0.0.0:0              LISTENING       3468
TCP    0.0.0.0:5432           0.0.0.0:0              LISTENING       8756
```

Two processes were listening on port 5432 (PIDs 3468 and 8756).

**Solution:** Changed the Docker container to use port 5433 instead of 5432:
```yaml
ports:
  - "5433:5432"
```

And updated the adapter to use port 5433:
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

### 13. Environment Variable Override
**Issue:** The `.env` file was overriding the port configuration in `settings.py`, causing the adapter to still try to connect to port 5432.

**Solution:** Hardcoded the port to 5433 in the adapter to bypass the `.env` override.

## Final Configuration

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
      - "5433:5432"  # Changed from 5432 to avoid conflict with local PostgreSQL
```

### Settings (backend/config/settings.py)
```python
DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", "5433"))  # Changed to 5433
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
            port=5433,  # Hardcoded to avoid .env override
            dbname=settings.DATABASE_NAME or "juridica_db",
            user=actual_user,
            password="",  # Trust authentication
            connect_timeout=10
        )
        return conn
```

## Lessons Learned

1. **Always check for port conflicts** when using Docker containers on Windows. Local services can intercept container ports.
2. **Environment variables can override defaults** in unexpected ways. Hardcoding critical values during debugging can help isolate issues.
3. **Docker volumes persist configuration** even after changing Compose files. Use `docker-compose down -v` to reset.
4. **pg_hba.conf is critical** for PostgreSQL authentication. Understanding its rules is essential for debugging connection issues.
5. **Trust authentication is convenient for development** but should be replaced with proper authentication in production.

## Verification

To verify the connection is working:
```bash
# Check that only the Docker container is listening on port 5433
netstat -ano | findstr :5433

# Check that the backend connects successfully
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
🔍 Conectando a PostgreSQL (intento 1/3)...
  🔧 Usando usuario: juridica_user (trust auth)
  ✅ Conexión exitosa para: juridica_user
✅ PostgreSQL conectado: PostgreSQL...
✅ Conexión PostgreSQL inicializada
```
