# SAT-Graph beta: chat y revisión del corpus

El corpus normativo versionado (SAT) es el motor por defecto, en local y en
producción. `pnpm dev` levanta backend y frontend sobre SAT; para comparar con
el grafo probabilístico heredado, `pnpm dev --lightrag`. Ambos motores usan el
backend en `localhost:8000` y el frontend en `localhost:3000`, uno a la vez.

La distribución beta incluye nueve fuentes procesadas: ocho fuentes normativas
recuperables y el Código de los Niños y Adolescentes como referencia documental
revisable. El corpus viaja con el repositorio:

- `backend/docs/sat_reviews/` contiene los PDF publicados (8 `source.pdf` y la
  referencia documental del CNA en `published-references/`).
- `backend/docs/sat_graph.pg_dump` es el respaldo PostgreSQL del corpus beta.

## Compartir el corpus en PostgreSQL

Por defecto, el chat SAT y el revisor leen y escriben en el esquema
`sat_graph` de **la misma base PostgreSQL del chat**. Para compartirlo, las
instancias del equipo deben apuntar al mismo `DATABASE_URL` (gestionado fuera de
Git); dos instancias Docker locales distintas no comparten datos. Tanto el chat
como el revisor deben tener acceso de lectura/escritura al esquema.

Para instalar el corpus beta en una base Docker local nueva, ejecuta:

```powershell
docker compose up -d --wait postgres
docker compose cp backend/docs/sat_graph.pg_dump postgres:/tmp/sat_graph.pg_dump
docker compose exec -T postgres pg_restore -U juridica_user -d juridica_db --single-transaction --exit-on-error --no-owner --no-privileges /tmp/sat_graph.pg_dump
```

Instala el respaldo una sola vez, sin usar `--clean`. Si el esquema ya existe,
no lo restaures encima. Para una base compartida, el administrador restaura
el mismo archivo con `pg_restore` apuntando a esa base. Después arranca con
`pnpm dev:full --sat`.
Los PDF originales siguen en `backend/docs/sat_reviews`; no se guardan como
binarios en PostgreSQL. Cada revisor necesita el checkout con esos PDF.

Si conservas una edición anterior en SQLite, puedes migrarla a una base vacía
con `uv run python backend/scripts/import_sat_postgres.py --from-sqlite RUTA`.
Ese comando es solo para migración; el chat y el revisor ya no usan SQLite.
Los candidatos previos pueden migrarse aparte con `--candidates`: sus PDF y
reportes de conversión todavía se consultan desde el directorio de trabajo.
La caché experimental de Voyage también usa PostgreSQL; si tienes una copia
anterior, `--voyage-cache` migra sus resultados y reservas sin llamar al proveedor.

El editor es una **herramienta administrativa independiente**, no una pantalla de
la página oficial. No arranca el chat, modelos, PostgreSQL ni Redis por sí solo.

## Abrir

Desde la raíz del proyecto:

```powershell
pnpm sat:review
```

Se abre el navegador en `127.0.0.1:8010`. La terminal imprime un enlace privado
que inicia la sesión local. No compartas ese enlace. El servidor solo escucha
en loopback; no permite acceso desde la red. Ctrl+C lo detiene.

Sin abrir automáticamente el navegador:

```powershell
uv run python backend/sat_review_app.py
```

Si prefieres usar el backend con `--sat`, `/sat-graph/review` requiere una sesión
con rol `admin`. La página pública y su navegación no se modifican.

## Corregir un documento

**Ver candidatos procesados** abre los PDF convertidos de la base aislada local
sin volver a ejecutar Docling. Se pueden corregir con las mismas herramientas.
**Publicar candidato** requiere confirmar el cotejo con el PDF. Los directorios,
anexos de normas ya publicadas y fuentes marcadas como incompletas pueden
publicarse como **referencias documentales**, sin entrar al recuperador normativo
ni reemplazar una edición existente. No se verifican fechas legales en este flujo.

1. Elige la norma en la biblioteca. La lista se enumera desde los CTV reales;
   no es un resultado de búsqueda limitado a los primeros fragmentos.
2. Revisa el árbol **Item / Work → Version / CTV → CLV / TextUnit**.
   Cada fila distingue si alimenta el recuperador o solo organiza el documento.
3. Selecciona una fila: modifica etiqueta, tipo, padre o texto completo.
   El inspector guarda los cambios automáticamente en el borrador de la pestaña.
   Si cambia la primera línea del texto, se actualiza la etiqueta. El chat no
   cambia hasta aplicar la revisión.
4. Para un artículo/inciso faltante, selecciona su texto en **Markdown completo**
   y pulsa **Crear componente con la selección**. Para eliminar un falso nodo,
   usa **Quitar nodo**: conserva el texto y reasigna sus hijos al padre.
5. Para agrupar componentes, marca las casillas de filas contiguas con el mismo
   padre actual y pulsa **Crear padre**. Revisa el nombre sugerido y el tipo.
   Los descendientes se conservan y no se modifica el Markdown.
6. Compara con **PDF original**. Su hash debe coincidir con la evidencia almacenada.
7. Pulsa **Aplicar al SAT-Graph** para publicar directamente, sin diálogo ni motivo manual.
   La siguiente consulta SAT ya usa la nueva edición, sin reiniciar.

**Borrador y aplicación no son lo mismo.** El borrador vive en la pestaña y se
puede exportar como JSON o Markdown. Al salir se advierte sobre cambios sin guardar.
El editor no reimporta automáticamente JSON descargados ni altera los PDF originales.

## Qué se guarda realmente

| Elemento | Resultado al aplicar |
|---|---|
| Markdown | Nueva `DocumentaryRevision` canónica dentro de la base SAT del chat |
| Componentes | Nuevos rangos y hashes, padre e hijos revisados |
| CTV y CLV | Nueva edición editorial, con textos recalculados desde el Markdown |
| Work / Item | Identidad estable para los componentes existentes |
| Edición anterior | Conservada y marcada `editorial_superseded_by`; excluida del recuperador |
| Auditoría | Origen de la aplicación, actor, instante de guardado y edición anterior completa |
| Evidencia original | PDF, `sat_documents` original y archivos de revisión anteriores intactos |
| Vigencia | No se consulta el reloj ni se inventan fechas legales |

Los padres contienen texto de los descendientes: corregir un inciso actualiza
también el texto recuperable de sus ancestros. Los rangos se miden en caracteres
Unicode, no bytes ni unidades UTF-16. Si una modificación cruza un límite ambiguo,
se rechaza y se pide corregir primero el componente menor o ajustar los rangos.

La publicación es una transacción: un error revierte todos los cambios. Un borrador
basado en otra edición recibe `409` y no sobrescribe la corrección más reciente.
El historial es auditable; no hay un botón de restauración automática por ahora.

**No reejecutes la importación de artefactos antiguos sobre una fuente editada.**
Los importadores detectan las ediciones del editor y se detienen para no perder
correcciones. Exporta el Markdown actualizado desde esta herramienta.

## API basada en SAT-Graph upstream

Base: [hmartim/sat-graph-api](https://github.com/hmartim/sat-graph-api), API 3.0.0,
commit `a767a3c47c654087288fd411b81ef2d8047e3696`, licencia MIT.
El bundle y licencia originales están en `docs/sat-api-upstream/`.

Implementamos un **subconjunto documentado**, no toda la especificación:

- Fetch y batch de `Item`, `Version`, `TextUnit`.
- Hijos y enumeración jerárquica de Items y Versions.
- Versiones almacenadas por Item, sin filtros históricos de intervalo.
- Introspección de tipos/aspectos y convenciones de implementación.

Prefijo: `/sat-graph/api`. La interfaz obtiene el texto mediante el primitivo
`POST /text-units/batch-get`. No usa búsqueda semántica para enumerar el corpus.
`GET /meta/implementation-guide` informa exactamente los límites y extensiones.
`/openapi.json` del servidor local publica los modelos y las operaciones reales.

Diferencias explícitas:

- Autenticación: sesión administrativa del proyecto, `X-API-Key` o sesión local
  privada; no el perfil `Authorization` del documento upstream.
- Intervalo desconocido: `[null, null]` con metadatos que lo indican. **No significa
  vigencia legal infinita.** La política de actualidad es el corpus mantenido.
- Edición/ingesta: extensión `/sat-graph/review`, fuera del contrato de lectura upstream.
- No se anuncian como implementadas causalidad, relaciones, búsqueda canónica
  probabilística, aplicabilidad ni filtros temporales históricos del upstream.

## Verificar sin modificar el corpus real

```powershell
uv run python -m pytest tests/backend/unit/test_sat_corpus_editor.py -q
```

El smoke visual `tests/frontend/e2e/sat-editor-smoke.mjs` publica una corrección:
ejecútalo **solo contra una base PostgreSQL aislada**, nunca contra el
corpus real. Requiere `SAT_EDITOR_TEST_COPY=1`, `SAT_EDITOR_URL` con el enlace
local y un navegador Playwright instalado (o `PLAYWRIGHT_CHANNEL=chrome`).

## Límites de la revisión

La herramienta muestra íntegramente lo **almacenado**. Esto no acredita que OCR o
Docling hayan extraído todas las páginas del PDF: los documentos incompletos
siguen requiriendo cotejo. La visualización no aprueba fuentes automáticamente.
Corpus con múltiples ediciones no unívocas o sin Markdown asociado se muestra
en lectura, sin permitir una publicación que descarte versiones inadvertidamente.

## Unidades de cambio y reversión

1. Publicación editorial + pruebas: servicio `sat_corpus`, filtro de ediciones
   archivadas en recuperador/store y guardas de importadores. No quitar el filtro
   si ya hay ediciones publicadas; conserva la base y exporta la edición actual.
2. API de lectura: adaptador `sat_api`, registro del router, bundle/licencia y
   pruebas de contrato. Puede retirarse sin alterar datos.
3. Interfaz/servidor local: recursos `static/sat-review`, rutas de revisión,
   `sat_review_app`, script `sat:review` y smoke visual. Retirarlos no borra el grafo.

No se modifican ni revierten cambios de evaluación u otros trabajos coexistentes.
