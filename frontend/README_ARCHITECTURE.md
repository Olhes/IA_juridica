# Frontend — arquitectura activa de v8

Actualización: **2026-10-06**. Next **16.3.8**, React **19.3.0**, Node **24**,
pnpm **10.30.2**; consulta `package.json`/`pnpm-lock.yaml` para el resto del stack.

## Flujo principal

`app/page.tsx` renderiza `ChatPage`; `app/layout.tsx` monta `AuthProvider` y
`ThemeProvider`, con idioma HTML español. `useChatSessions` gestiona conversaciones
y `useChat` consume NDJSON de `/legal-query-stream`. `apiService` gestiona el resto
de peticiones. Se llama **directamente** al backend configurado por
`NEXT_PUBLIC_API_URL`, incluyendo cookies; no hay una pasarela activa `app/api`.

```powershell
# Desde raíz, después de instalar ambos paquetes Node
pnpm frontend:dev
pnpm frontend:build
pnpm frontend:start
```

Configura `frontend/.env.local` con `NEXT_PUBLIC_API_URL=http://localhost:8000`.
Las variables `NEXT_PUBLIC_*` forman parte del build: reconstruye al cambiarlas.
Nunca pongas `ADMIN_API_KEY`, claves de modelos ni secretos JWT en ese entorno público.

## Responsabilidades

| Ruta | Responsabilidad |
|---|---|
| `src/domain/legal/` | Tipos compartidos de mensajes/consultas |
| `src/application/legal/services/` | API y cuenta OAuth; notificación de estado |
| `src/application/legal/use-cases/` | Estado de chat, sesiones, abort y carga |
| `src/presentation/components/` | Animación, providers, radial hub, chat y sidebar |
| `src/presentation/pages/ChatPage.tsx` | Pantalla principal y coordinación |
| `app/login/`, `app/register/`, `app/auth/callback/` | Rutas de login, redirección y callback |

El callback guarda `auth_just_logged_in` como **indicador UI**, no token.
Las credenciales usan cookies del backend. `ProtectedRoute` espera hidratación;
su control visual no sustituye autorización en servidor. Cuenta OAuth y principal
anónimo del chat están separados: no se promete migración de historial.

## Código heredado

`LegalAssistantPage`, `useBackendChat` y `usePersistentChat` se conservan como
alternativas, pero no los usa el entrypoint principal. `/register` redirige a
login; no hay formulario de registro activo. `LoginPage` aún contiene URL OAuth
local fija: no basta cambiar `NEXT_PUBLIC_API_URL` para esa pantalla heredada.
Antes de producción revisa [OAuth](../OAUTH_SETUP.md).

## Verificar cambios

Desde raíz: `pnpm test:frontend`, `pnpm test:frontend:coverage`, `pnpm test:e2e`.
Tests centralizados en `tests/frontend/`; [guía única](../tests/README.md).
Vitest ejercita componentes/hooks reales con API simulada; Playwright usa API
simulada salvo opt-in explícito. Ninguno demuestra calidad jurídica del modelo.
No excluyas módulos heredados o animaciones para inflar cobertura.
