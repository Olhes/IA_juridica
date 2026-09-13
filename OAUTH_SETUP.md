# Configuración de Google OAuth 2.0 para IA Jurídica

## Resumen

Esta guía explica cómo configurar el inicio de sesión con Google OAuth 2.0 para la aplicación IA Jurídica.

**Nota de Seguridad**: Esta implementación usa **httpOnly cookies** para almacenar tokens JWT, lo cual es mucho más seguro que localStorage. Las cookies httpOnly no son accesibles desde JavaScript, previniendo ataques XSS.

## Pasos de Configuración

### 1. Crear Proyecto en Google Cloud Console

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto o selecciona uno existente
3. Navega a **APIs & Services** > **Credentials**

### 2. Configurar OAuth 2.0 Consent Screen

1. Haz clic en **OAuth consent screen**
2. Selecciona **External** (para usuarios externos)
3. Completa la información requerida:
   - **App name**: IA Jurídica
   - **User support email**: tu email
   - **Developer contact information**: tu email
4. Haz clic en **Save and Continue**
5. En **Scopes**, agrega:
   - `openid`
   - `email`
   - `profile`
6. Haz clic en **Save and Continue**
7. En **Test users**, agrega tu email para pruebas
8. Haz clic en **Save and Continue**

### 3. Crear Credenciales OAuth 2.0

1. Ve a **Credentials** > **Create Credentials** > **OAuth client ID**
2. Selecciona **Web application**
3. Configura:

**Authorized JavaScript Origins** (solo dominio base, sin ruta):
- `http://localhost:3000` (desarrollo)
- `https://ia-juridica-frontend-web.onrender.com` (producción)

**Authorized Redirect URIs** (dominio + ruta completa del BACKEND):
- `http://localhost:8000/auth/google/callback` (desarrollo)
- `https://tu-backend-dominio.com/auth/google/callback` (producción)

4. Haz clic en **Create**
5. Copia el **Client ID** y **Client Secret**

### 4. Configurar Variables de Entorno

En el archivo `backend/.env`, agrega:

```bash
# Google OAuth 2.0
GOOGLE_CLIENT_ID=tu_client_id_aqui
GOOGLE_CLIENT_SECRET=tu_client_secret_aqui
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
GOOGLE_FRONTEND_CALLBACK_URI=http://localhost:3000/auth/callback
```

Para producción:
```bash
GOOGLE_REDIRECT_URI=https://tu-backend-dominio.com/auth/google/callback
GOOGLE_FRONTEND_CALLBACK_URI=https://ia-juridica-frontend-web.onrender.com/auth/callback
```

### 5. Ejecutar Migración de Base de Datos

Para agregar el campo `picture` a la tabla de usuarios (necesario para mostrar el avatar de Google):

```bash
# Desde la raíz del proyecto
psql -U juridica_user -d juridica_db -h localhost -p 5433 -f backend/database/migrations/002_add_picture_column.sql
```

O manualmente:
```sql
ALTER TABLE auth_schema.users ADD COLUMN IF NOT EXISTS picture VARCHAR(500);
```

### 6. Verificar Configuración en Frontend

El botón de login en `ChatHeader.tsx` redirige directamente al backend:

```typescript
const handleAuth = () => {
  if (isAuthenticated) {
    logout();
  } else {
    // Iniciar Google OAuth directamente
    window.location.href = 'http://localhost:8000/auth/google';
  }
};
```

Para producción, cambia a tu dominio del backend:
```typescript
window.location.href = 'https://api.tu-dominio.com/auth/google';
```

## Flujo de Autenticación (con httpOnly Cookies)

1. Usuario hace clic en "Acceder" en el header
2. Frontend redirige a `/auth/google` del backend
3. Backend redirige a Google OAuth consent screen
4. Usuario autoriza la aplicación
5. Google redirige al callback del backend con un código
6. Backend intercambia el código por tokens de acceso
7. Backend obtiene información del usuario desde Google (email, nombre, avatar)
8. Backend crea o actualiza el usuario en PostgreSQL (incluyendo avatar)
9. Backend genera tokens JWT
10. **Backend establece cookies httpOnly** (más seguro que localStorage)
11. Backend redirige al frontend (`/auth/callback`)
12. Frontend establece flag en localStorage y redirige a `/`
13. AuthProvider detecta el flag y re-verifica autenticación con el backend
14. Header muestra avatar de Google y nombre del usuario

## Características Implementadas

- ✅ **Avatar de Google**: La foto de perfil de Google se muestra en el header
- ✅ **Nombre completo**: Se muestra el nombre completo del usuario de Google
- ✅ **Botón "Acceder"**: Texto simplificado en lugar de "Continuar con Google"
- ✅ **Sin animación intermedia**: Callback redirige directamente sin mostrar loading
- ✅ **Actualización de usuario**: Usuarios existentes se actualizan con datos de Google
- ✅ **Sesión persistente**: La sesión permanece hasta cerrar sesión o detener el servidor
- ✅ **Detección automática**: AuthProvider detecta autenticación después del callback

## Diferencia con Implementación Anterior

**Anterior (inseguro)**:
- Tokens en URL del callback
- Tokens guardados en localStorage
- Vulnerable a ataques XSS

**Actual (seguro)**:
- Tokens en cookies httpOnly
- Cookies enviadas automáticamente por el navegador
- No accesibles desde JavaScript
- Protegido contra ataques XSS

## Solución de Problemas

### Error: "Google OAuth no está configurado"

- Verifica que `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` estén en `backend/.env`
- Reinicia el servidor del backend

### Error: "redirect_uri_mismatch"

- Verifica que el redirect URI en Google Cloud Console coincida exactamente con `GOOGLE_REDIRECT_URI` (backend callback)
- Asegúrate de incluir el protocolo (http:// o https://)

### Error: "column picture does not exist"

- Ejecuta la migración SQL: `psql -U juridica_user -d juridica_db -h localhost -p 5433 -f backend/database/migrations/002_add_picture_column.sql`

### Error: "access_denied"

- Verifica que tu email esté en la lista de usuarios de prueba (si el consent screen está en modo Testing)
- O publica la aplicación para producción

### Error: Cookies no funcionan en desarrollo

- Verifica que `secure=False` en las cookies para desarrollo (HTTP)
- En producción, cambia a `secure=True` para HTTPS
- Verifica CORS settings en el backend

### El usuario no aparece como autenticado después del login

- Verifica que el AuthProvider esté escuchando cambios en localStorage
- Revisa la consola del navegador para logs de autenticación
- Verifica que las cookies se estén estableciendo en el backend

## Seguridad

- **Nunca** commits el archivo `.env` con credenciales reales
- Usa variables de entorno para todas las credenciales sensibles
- En producción, usa HTTPS obligatoriamente y `secure=True` en cookies
- Limita los scopes a lo mínimo necesario (openid, email, profile)
- Revisa regularmente las credenciales en Google Cloud Console
- Las cookies httpOnly previenen ataques XSS
- Las cookies con `samesite=lax` previenen ataques CSRF
