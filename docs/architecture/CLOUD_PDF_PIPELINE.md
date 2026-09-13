# Cloud PDF Pipeline (sin versionar PDFs)

## Objetivo
Procesar documentos PDF fuera del repositorio Git, con almacenamiento y procesamiento cloud escalable.

## Arquitectura propuesta

1. **Object Storage**
   - AWS S3, Google Cloud Storage o Cloudflare R2.
   - Buckets/prefixes sugeridos:
     - `raw/` (PDF original)
     - `processed/` (markdown Docling)
     - `failed/` (errores)

2. **API de orquestación (FastAPI)**
   - Genera URL firmada para upload.
   - Crea `document_id` y metadata inicial.
   - Consulta estado del procesamiento.

3. **Cola de mensajes**
   - AWS SQS / GCP Pub/Sub / RabbitMQ.
   - Mensaje mínimo: `document_id`, `object_key`, `tenant_id`, `uploaded_at`.

4. **Worker Python**
   - Descarga PDF desde object storage.
   - Ejecuta Docling + pipeline de ingestión.
   - Inserta/actualiza en LightRAG.
   - Sube artefactos y actualiza estado.

5. **Base de datos de control**
   - PostgreSQL para trazabilidad e idempotencia.
   - Tabla sugerida: `documents` (`id`, `status`, `sha256`, `source_key`, `error`, `created_at`, `updated_at`).

## Flujo end-to-end

```text
Frontend -> FastAPI /documents/presign-upload -> URL firmada
Frontend -> PUT PDF a object storage
Storage Event o API callback -> Queue
Worker -> descarga PDF -> Docling -> LightRAG -> guarda artefactos
Worker -> PostgreSQL status=processed|failed
Frontend -> FastAPI /documents/{id}/status
```

## Endpoints sugeridos

- `POST /documents/presign-upload`
  - input: `filename`, `content_type`, `topic`
  - output: `document_id`, `upload_url`, `object_key`
- `POST /documents/ingest-from-object`
  - input: `document_id`
  - acción: publica en cola
- `GET /documents/{document_id}/status`
  - output: `uploaded|queued|processing|processed|failed`
- `POST /documents/{document_id}/reprocess`
  - acción: reproceso controlado

## Reglas de seguridad

- URL firmada con expiración corta (5-15 min).
- Sin credenciales cloud en frontend.
- Bucket privado + cifrado en reposo.
- Validar MIME y tamaño antes de encolar.
- Antivirus opcional (ClamAV/Lambda scan) antes de procesar.

## Cambios mínimos para este repo

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
3. **Fase 3:** migrar históricos y purgar PDFs del repositorio.
