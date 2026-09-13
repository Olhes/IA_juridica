-- Agregar columna picture a la tabla users para Google OAuth
-- Ejecutar: psql -U juridica_user -d juridica_db -f database/migrations/002_add_picture_column.sql

ALTER TABLE auth_schema.users 
ADD COLUMN IF NOT EXISTS picture VARCHAR(500);

-- Agregar índice para búsquedas por picture (opcional)
CREATE INDEX IF NOT EXISTS idx_users_picture ON auth_schema.users(picture) WHERE picture IS NOT NULL;
