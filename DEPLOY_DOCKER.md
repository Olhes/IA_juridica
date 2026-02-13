# Deploy to production with Docker

This project now includes production-ready container files for backend and frontend.

## Files added

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `docker-compose.prod.yml`
- `env.production.example`
- `.dockerignore`

## 1) Prepare environment variables

Create your production env file from the example:

```bash
cp env.production.example .env.production
```

Then edit `.env.production` with real values, especially:

- `OPENAI_API_KEY`
- `SECRET_KEY`
- `CORS_ORIGINS`

## 2) Build and run

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

## 3) Verify

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
```

## 4) Update deploy

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

## 5) Basic hardening checklist

- Put a reverse proxy in front (Nginx/Caddy/Traefik) with HTTPS.
- Restrict `CORS_ORIGINS` to your real domains.
- Keep `.env.production` out of git.
- Add external backups for `backend_docs` volume if you need document persistence.

## Notes

- Backend docs and graph artifacts are persisted in Docker volumes: `backend_docs`.
- Backend logs are persisted in Docker volume: `backend_logs`.
- Frontend talks to backend through `FASTAPI_BASE_URL=http://backend:8000` inside the Docker network.
