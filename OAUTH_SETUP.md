# OAuth local y limitaciones — rama v8

Actualización: **2026-10-06**. Configuración del módulo existente, **no guía de
despliegue seguro sin cambios adicionales**.

## Configuración local

Usa credenciales de cliente web Google y registra la URL exacta de callback del
backend. Guarda en `backend/.env`, nunca en frontend/Git:

```dotenv
GOOGLE_CLIENT_ID=<cliente>
GOOGLE_CLIENT_SECRET=<secreto>
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
GOOGLE_FRONTEND_CALLBACK_URI=http://localhost:3000/auth/callback
```

Adapta ambas URLs al dominio del entorno sin mezclar callback backend y frontend.
El flujo solicita `openid email profile`. La base necesita `auth_schema` y campo
`picture`; el repositorio contiene `backend/database/migrations/002_add_picture_column.sql`.
Ejecuta migraciones revisadas con backup, no recrees volúmenes para añadir columnas.

## Qué implementa

`/auth/google` redirige al proveedor; `/auth/google/callback` intercambia código,
consulta perfil y crea/actualiza usuario PostgreSQL, incluidos nombre/avatar.
Emite tokens en cookies. `/auth/me` consulta la cuenta, `/auth/refresh` renueva
access token, `/auth/logout` elimina cookies. El frontend callback conserva solo
`auth_just_logged_in` como indicador visual y vuelve a `/`.
El login de la pantalla heredada `LoginPage` sigue con URL local fija; revisa
todos los entrypoints antes de afirmar que `NEXT_PUBLIC_API_URL` cubre OAuth.

## Límites que impiden prometer producción segura

- HttpOnly evita lectura de cookies por JavaScript, **no elimina XSS** ni otras
  formas de abuso desde el navegador.
- Las rutas login/refresh heredadas incluyen `secure=False`; no asumas que la
  configuración Secure del principal anónimo también endurece estas cookies.
- El parámetro `state` de callback no constituye validación de estado OAuth:
  el flujo actual requiere endurecimiento explícito y pruebas de rechazo.
- Existe `/auth/reset-admin-password`, endpoint temporal con credenciales/hash
  conocidos en la respuesta: no debe exponerse en un despliegue público.
- El principal anónimo del chat y la cuenta OAuth están separados. No se migra
  automáticamente el historial al iniciar sesión ni se convierte su propietario.

Estas limitaciones se documentan, no quedan corregidas por actualizar esta guía.
Consulta [seguridad](docs/SECURITY.md), [API](API_DOC.md) y [tests](tests/README.md).
