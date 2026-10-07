# Diagnosticar PostgreSQL — v8

Actualización: **2026-10-06**. Sustituye recetas históricas destructivas o basadas
en `trust` para producción. No borres datos para solucionar conectividad.

## Identificar desde dónde conecta el backend

| Backend ejecutándose… | Host / puerto del Compose de desarrollo |
|---|---|
| En Windows/host | `localhost:5433` |
| En la misma red Compose | `postgres:5432` |

El contenedor se llama `ia_juridica_postgres`, base `juridica_db`, usuario
`juridica_user`. El Compose de desarrollo publica `127.0.0.1:5433:5432` para evitar
conflicto con PostgreSQL local en 5432. Verifica configuración efectiva: no supongas
que dos puertos llegan a la misma instancia.

```powershell
docker compose ps postgres
docker compose logs --tail 50 postgres
docker compose exec postgres pg_isready -U juridica_user -d juridica_db
```

Revisa `backend/.env`, `DATABASE_URL` y variables `DATABASE_HOST`, `DATABASE_PORT`,
`DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`. Una URL configurada tiene
precedencia en el adaptador; no publiques logs/URLs con contraseñas.
El chat usa `backend/database/postgres_adapter_final.py`, no SQLite.

## Errores frecuentes

- **Connection refused**: servicio no listo, puerto equivocado, red o firewall.
- **Authentication failed**: estás en otra instancia o el volumen tiene credenciales
  antiguas. Cambiar `POSTGRES_PASSWORD` no modifica automáticamente usuarios ya creados.
- **Relation/column missing**: revisa schemas/migraciones aplicadas y `picture`
  para OAuth; no es un problema de password.
- **API degraded/503**: `/health` diferencia PostgreSQL/corpus; `/ready` mide
  corpus y no es un diagnóstico completo de la conexión DB.

El Compose local tiene `trust` y password de prueba. No copies esa configuración
a producción ni añadas reglas `0.0.0.0/0 trust` para resolver autenticación.
Usa red privada, autenticación y secretos propios. **No ejecutes `down -v` ni
`docker volume rm` sin backup y aprobación de pérdida de datos.**
Los tests SQL simulados comprueban owner/rollback, no sustituyen una prueba contra
PostgreSQL real ni verifican permisos y migraciones del servidor.
[Despliegue](DEPLOY_RENDER.md) · [Tests](tests/README.md).
