"""Shared connection settings for chat persistence and the SAT schema."""
import psycopg

from config.settings import settings


def connect_postgres():
    url = settings.DATABASE_URL or ""
    if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=10)
    if settings.ENVIRONMENT == "production":
        raise ValueError("Configure DATABASE_URL con una conexión PostgreSQL")
    # Compatibility with existing developer .env files that specify SQLite.
    return psycopg.connect(host=settings.DATABASE_HOST or "localhost", port=settings.DATABASE_PORT,
                           dbname=settings.DATABASE_NAME or "juridica_db", user=settings.DATABASE_USER,
                           password=settings.DATABASE_PASSWORD,
                           connect_timeout=10)
