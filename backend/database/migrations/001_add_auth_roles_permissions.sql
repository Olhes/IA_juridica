-- Migración: Agregar password_hash y sistema de roles/permisos
-- Ejecutar después de init_multi_schema.sql

-- ========================================
-- AUTH_SCHEMA - Modificaciones y Nuevas Tablas
-- ========================================

-- Agregar password_hash a tabla users
ALTER TABLE auth_schema.users 
ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- Crear tabla de roles
CREATE TABLE IF NOT EXISTS auth_schema.roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    permissions JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Crear tabla de permisos individuales
CREATE TABLE IF NOT EXISTS auth_schema.permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    resource VARCHAR(50) NOT NULL, -- 'chat', 'documents', 'admin', etc.
    action VARCHAR(50) NOT NULL, -- 'read', 'write', 'delete', 'manage'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Crear tabla de relación usuario-rol (muchos a muchos)
CREATE TABLE IF NOT EXISTS auth_schema.user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth_schema.users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES auth_schema.roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_by UUID REFERENCES auth_schema.users(id),
    UNIQUE(user_id, role_id)
);

-- Crear tabla de relación rol-permiso (muchos a muchos)
CREATE TABLE IF NOT EXISTS auth_schema.role_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_id UUID NOT NULL REFERENCES auth_schema.roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES auth_schema.permissions(id) ON DELETE CASCADE,
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(role_id, permission_id)
);

-- ========================================
-- ROLES PREDEFINIDOS
-- ========================================

-- Rol: admin (acceso total)
INSERT INTO auth_schema.roles (name, description) 
VALUES ('admin', 'Administrador con acceso total al sistema')
ON CONFLICT (name) DO NOTHING;

-- Rol: user (usuario básico)
INSERT INTO auth_schema.roles (name, description) 
VALUES ('user', 'Usuario básico con acceso limitado')
ON CONFLICT (name) DO NOTHING;

-- ========================================
-- PERMISOS PREDEFINIDOS
-- ========================================

-- Permisos de chat
INSERT INTO auth_schema.permissions (name, description, resource, action) 
VALUES 
    ('chat:read', 'Leer conversaciones', 'chat', 'read'),
    ('chat:write', 'Crear y enviar mensajes', 'chat', 'write'),
    ('chat:delete', 'Eliminar conversaciones', 'chat', 'delete'),
    ('chat:manage', 'Gestionar conversaciones de otros usuarios', 'chat', 'manage')
ON CONFLICT (name) DO NOTHING;

-- Permisos de documentos
INSERT INTO auth_schema.permissions (name, description, resource, action) 
VALUES 
    ('documents:read', 'Leer documentos', 'documents', 'read'),
    ('documents:write', 'Subir y procesar documentos', 'documents', 'write'),
    ('documents:delete', 'Eliminar documentos', 'documents', 'delete'),
    ('documents:manage', 'Gestionar documentos del sistema', 'documents', 'manage')
ON CONFLICT (name) DO NOTHING;

-- Permisos administrativos
INSERT INTO auth_schema.permissions (name, description, resource, action) 
VALUES 
    ('admin:users', 'Gestionar usuarios', 'admin', 'users'),
    ('admin:roles', 'Gestionar roles y permisos', 'admin', 'roles'),
    ('admin:system', 'Configuración del sistema', 'admin', 'system')
ON CONFLICT (name) DO NOTHING;

-- ========================================
-- ASIGNAR PERMISOS A ROLES
-- ========================================

-- Admin: todos los permisos
INSERT INTO auth_schema.role_permissions (role_id, permission_id)
SELECT r.id, p.id 
FROM auth_schema.roles r, auth_schema.permissions p 
WHERE r.name = 'admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- User: solo permisos de chat
INSERT INTO auth_schema.role_permissions (role_id, permission_id)
SELECT r.id, p.id 
FROM auth_schema.roles r, auth_schema.permissions p 
WHERE r.name = 'user' 
AND p.name IN ('chat:read', 'chat:write')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- ========================================
-- ÍNDICES
-- ========================================

CREATE INDEX IF NOT EXISTS idx_auth_users_password ON auth_schema.users(password_hash);
CREATE INDEX IF NOT EXISTS idx_auth_user_roles_user ON auth_schema.user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_user_roles_role ON auth_schema.user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_auth_role_permissions_role ON auth_schema.role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_auth_role_permissions_permission ON auth_schema.role_permissions(permission_id);
