-- Seed: Usuario Admin Inicial
-- Ejecutar después de 001_add_auth_roles_permissions.sql

-- Insertar usuario admin
-- Password: admin123 (hasheado con bcrypt)
-- Para generar un nuevo hash: python -c "from passlib.context import CryptContext; pwd = CryptContext(schemes=['bcrypt'], deprecated='auto'); print(pwd.hash('tu_password'))"

INSERT INTO auth_schema.users (email, username, password_hash, full_name, role, is_active)
VALUES (
    'admin@iajuridica.pe',
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7bXqL0f1eS', -- bcrypt hash de "admin123"
    'Administrador del Sistema',
    'admin',
    true
) ON CONFLICT (email) DO NOTHING;

-- Asignar rol admin al usuario admin
INSERT INTO auth_schema.user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id,
    r.id,
    u.id
FROM auth_schema.users u, auth_schema.roles r
WHERE u.email = 'admin@iajuridica.pe' AND r.name = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Insertar usuario básico de prueba
INSERT INTO auth_schema.users (email, username, password_hash, full_name, role, is_active)
VALUES (
    'user@iajuridica.pe',
    'user_test',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7bXqL0f1eS', -- bcrypt hash de "admin123"
    'Usuario de Prueba',
    'user',
    true
) ON CONFLICT (email) DO NOTHING;

-- Asignar rol user al usuario básico
INSERT INTO auth_schema.user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id,
    r.id,
    (SELECT id FROM auth_schema.users WHERE email = 'admin@iajuridica.pe')
FROM auth_schema.users u, auth_schema.roles r
WHERE u.email = 'user@iajuridica.pe' AND r.name = 'user'
ON CONFLICT (user_id, role_id) DO NOTHING;
