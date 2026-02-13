# Frontend Architecture (TypeScript)

El frontend usa Next.js App Router con una separacion por capas:

- `src/domain`: tipos del negocio y puertos (interfaces).
- `src/application`: casos de uso (orquestacion de reglas).
- `src/infrastructure`: adaptadores HTTP para FastAPI.
- `src/presentation`: UI (paginas, componentes, i18n).
- `app/api`: rutas servidor de Next.js que delegan al backend FastAPI.

## Flujo principal

1. UI ejecuta un caso de uso (`application`).
2. El caso de uso llama un puerto (`domain`).
3. Un gateway HTTP (`infrastructure`) implementa ese puerto.
4. El gateway consume `app/api/legal/*`.
5. `app/api/legal/*` reenvia la solicitud a FastAPI.
