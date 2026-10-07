# Arquitectura del frontend (TypeScript)

El frontend usa Next.js App Router con una separación por capas:

- `src/domain`: tipos del negocio y puertos (interfaces).
- `src/application`: casos de uso (orquestacion de reglas).
- `src/infrastructure`: adaptadores HTTP para FastAPI.
- `src/presentation`: UI (paginas, componentes, i18n).
- `app/api`: rutas servidor de Next.js que delegan al backend FastAPI.

## Flujo principal

1. La interfaz ejecuta un caso de uso (`application`).
2. El caso de uso llama a un puerto (`domain`).
3. Una puerta de enlace HTTP (`infrastructure`) implementa ese puerto.
4. El gateway consume `app/api/legal/*`.
5. `app/api/legal/*` reenvía la solicitud a FastAPI.
