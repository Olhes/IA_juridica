-- Inicialización de base de datos para IA Jurídica
-- Este script se ejecuta automáticamente cuando se crea el contenedor PostgreSQL

-- Crear extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Crear esquema principal si no existe
CREATE SCHEMA IF NOT EXISTS juridica_schema;

-- Otorgar permisos
GRANT ALL PRIVILEGES ON SCHEMA juridica_schema TO juridica_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA juridica_schema TO juridica_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA juridica_schema TO juridica_user;

-- Establecer schema por defecto para el usuario
ALTER ROLE juridica_user SET search_path TO juridica_schema, public;
