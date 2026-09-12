-- Fix: Actualizar password del usuario admin existente
-- Password: admin123 (hasheado con bcrypt)

-- Actualizar password del usuario admin
UPDATE auth_schema.users 
SET password_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7bXqL0f1eS'
WHERE email = 'admin@iajuridica.pe';

-- Asegurar que el usuario admin esté activo
UPDATE auth_schema.users 
SET is_active = true 
WHERE email = 'admin@iajuridica.pe';

-- Asignar rol admin al usuario admin (si no está asignado)
INSERT INTO auth_schema.user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id,
    r.id,
    u.id
FROM auth_schema.users u, auth_schema.roles r
WHERE u.email = 'admin@iajuridica.pe' AND r.name = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Verificar usuario
SELECT id, email, username, is_active FROM auth_schema.users WHERE email = 'admin@iajuridica.pe';
