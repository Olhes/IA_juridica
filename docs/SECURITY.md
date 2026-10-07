# Modelo de seguridad

Alcance revisado: **rama v8 · 2026-10-06**. Este documento describe controles
del principal anónimo; no acredita que todos los módulos estén endurecidos.
El módulo de cuentas OAuth heredado conserva riesgos pendientes de cookies,
estado OAuth y endpoint temporal de reset: [alcance y limitaciones](../OAUTH_SETUP.md).
Esas rutas no comparten automáticamente identidad ni historial con el chat anónimo.

## Identidad anónima

El backend emite una sesión HMAC-SHA256 versionada y con vencimiento en la
cookie `ia_juridica_session`. La cookie es `HttpOnly`, usa `SameSite=Lax` de
forma predeterminada y siempre tiene el atributo `Secure` en producción. Los
clientes la inicializan con `POST /session/bootstrap`; ni el cuerpo de la
solicitud ni los parámetros de consulta determinan la identidad propietaria.

El navegador puede guardar en el almacenamiento local preferencias de interfaz
no sensibles, como el idioma, el alias o indicaciones de instalación. El
almacenamiento local no es un mecanismo de autenticación y no debe contener
tokens bearer, tokens de sesión, prompts, respuestas ni identificadores de
propiedad de conversaciones.

Las conversaciones permanecen en PostgreSQL y Redis. Cada clave de caché de
conversación y cada operación SQL de lectura o escritura incluye la identidad
derivada de la cookie. Los identificadores ajenos y desconocidos de
conversaciones devuelven la misma respuesta 404.

## Configuración obligatoria en producción

- Establecer `ENVIRONMENT=production`.
- Asignar a `ANONYMOUS_SESSION_SECRET` al menos 32 bytes aleatorios. No reutilizar
  `SECRET_KEY` ni `ADMIN_API_KEY`.
- Al ejecutar varios workers, configurar `RATE_LIMIT_STORAGE_URI` para usar un
  almacenamiento compartido, normalmente Redis.
- Enumerar los orígenes exactos en `CORS_ORIGINS`; la validación de inicio
  rechaza comodines en orígenes, métodos y encabezados.
- Mantener `ADMIN_ENDPOINTS_ENABLED=false` salvo que se necesite administración.
  Si se habilita, definir una `ADMIN_API_KEY` independiente y enviarla en
  `X-API-Key`.
- La documentación de la API y OpenAPI están deshabilitados de forma
  predeterminada en producción. Habilitarlos deliberadamente con
  `API_DOCS_ENABLED=true`.

En desarrollo local, `http://localhost:3000` y `http://localhost:8000` tienen
orígenes distintos, pero pertenecen al mismo sitio; por ello funciona
`SameSite=Lax` junto con `credentials: include`. Si el frontend y la API de
producción usan dominios registrables distintos, se requiere
`SameSite=None; Secure`, lo que introduce exposición a CSRF. Se recomienda usar
un subdominio de API del mismo sitio o un proxy inverso. Si el despliegue entre
sitios es inevitable, añadir protección explícita contra CSRF antes de cambiar
la configuración de la cookie.

## Conversaciones de demostración existentes

Las filas existentes asociadas al UUID histórico de demostración son
deliberadamente inaccesibles para nuevos visitantes anónimos. Nunca se asignan
automáticamente. Un operador puede previsualizar y luego reasignar
explícitamente una identidad propietaria conocida a una identidad elegida:

```powershell
uv run python backend/scripts/reassign_conversation_owner.py `
  --source-owner <historical-owner-uuid> `
  --new-owner <principal-id-from-bootstrap>

uv run python backend/scripts/reassign_conversation_owner.py `
  --source-owner <historical-owner-uuid> `
  --new-owner <principal-id-from-bootstrap> `
  --apply --confirm REASSIGN-CONVERSATIONS
```

Primero ejecutar el modo de simulación y crear una copia de seguridad de
PostgreSQL. La utilidad actualiza únicamente las filas cuyo propietario actual
coincide exactamente con `--source-owner`; los mensajes se actualizan mediante
la clave foránea de su conversación. Después de aplicar la migración, borrar
solo las claves de caché de conversaciones de la identidad afectada.

## Cargas de archivos

Las cargas de PDF administrativas requieren que la API de administración esté
habilitada y que la clave sea válida. El backend genera el nombre base del
archivo almacenado, escribe en disco en modo de flujo respetando
`MAX_FILE_SIZE`, verifica la extensión `.pdf`, el tipo de medio
`application/pdf` y la firma `%PDF-`, crea el archivo de forma exclusiva y
elimina los archivos parciales originales o procesados si ocurre un error. El
nombre base original saneado se conserva únicamente como metadato.
