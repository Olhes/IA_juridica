# Procesamiento de PDF en la nube (sin versionar los PDF)

## Objetivo
Procesar documentos PDF fuera del repositorio Git, con almacenamiento y procesamiento escalables en la nube.

## Arquitectura propuesta

1. **Almacenamiento de objetos**
   - AWS S3, Google Cloud Storage o Cloudflare R2.
   - Buckets/prefijos sugeridos:
     - `raw/` (PDF original)
     - `processed/` (markdown Docling)
     - `failed/` (errores)

2. **API de orquestación (FastAPI)**
   - Genera una URL firmada para la carga.
   - Crea `document_id` y metadatos iniciales.
   - Consulta el estado del procesamiento.

3. **Cola de mensajes**
   - AWS SQS / GCP Pub/Sub / RabbitMQ.
   - Mensaje mínimo: `document_id`, `object_key`, `tenant_id`, `uploaded_at`.

4. **Worker de Python**
   - Descarga el PDF del almacenamiento de objetos.
   - Ejecuta Docling y el pipeline de ingesta.
   - Inserta o actualiza datos en LightRAG.
   - Carga los artefactos y actualiza el estado.

5. **Base de datos de control**
   - PostgreSQL para trazabilidad e idempotencia.
   - Tabla sugerida: `documents` (`id`, `status`, `sha256`, `source_key`, `error`, `created_at`, `updated_at`).

## Flujo integral

```text
Interfaz -> FastAPI /documents/presign-upload -> URL firmada
Interfaz -> PUT PDF en el almacenamiento de objetos
Evento de almacenamiento o callback de API -> cola
Proceso -> descarga PDF -> Docling -> LightRAG -> guarda artefactos
Proceso -> PostgreSQL status=processed|failed
Interfaz -> FastAPI /documents/{id}/status
```

## Endpoints sugeridos

- `POST /documents/presign-upload`
  - Entrada: `filename`, `content_type`, `topic`
  - Salida: `document_id`, `upload_url`, `object_key`
- `POST /documents/ingest-from-object`
  - Entrada: `document_id`
  - Acción: publica un mensaje en la cola
- `GET /documents/{document_id}/status`
  - Salida: `uploaded|queued|processing|processed|failed`
- `POST /documents/{document_id}/reprocess`
  - acción: reproceso controlado

## Reglas de seguridad

- URL firmada con expiración corta (5-15 min).
- Sin credenciales cloud en frontend.
- Bucket privado + cifrado de datos en reposo.
- Validar MIME y tamaño antes de encolar.
- Antivirus opcional (ClamAV/Lambda scan) antes de procesar.

## Cambios mínimos para este repositorio

1. Mantener `backend/docs/*` solo para desarrollo local.
2. Añadir capa `storage_provider` (S3/GCS/R2) en backend.
3. Añadir worker `backend/workers/pdf_ingestion_worker.py`.
4. Añadir metadata de documentos en PostgreSQL.
5. Conectar frontend Next.js a endpoints de URL firmada y estado.

## Alternativas de infraestructura

- **AWS:** S3 + SQS + ECS Fargate/Lambda + RDS PostgreSQL.
- **GCP:** GCS + Pub/Sub + Cloud Run + Cloud SQL.
- **Cloudflare stack:** R2 + Queues + Workers + D1/Postgres externo.

## Estrategia de adopción

1. **Fase 1:** dual mode (local + cloud) con feature flag.
2. **Fase 2:** producción solo cloud para PDFs nuevos.
3. **Fase 3:** migrar los documentos históricos y eliminar los PDF del repositorio.
