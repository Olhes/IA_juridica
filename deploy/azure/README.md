# Deploy: backend en Azure VM + frontend en Vercel

```
Navegador ──> https://ia-juridica-pe.vercel.app  (Next.js en Vercel)
                 └─ /api/*  ──rewrite──> https://api.68-211-120-105.sslip.io  (Caddy, HTTPS)
                                              └─> backend:8000 (FastAPI, 1 worker)
                                                   ├─ postgres (volumen postgres_data)
                                                   ├─ redis    (volumen redis_data)
                                                   └─ docs/knowledge_graph (corpus del repo)
```

El navegador solo habla con el dominio de Vercel, así que las cookies de sesión
(anónima y de Google) son first-party y no hace falta CORS cross-site.

| Qué | Valor |
|---|---|
| VM | `azureuser@68.211.120.105` (Ubuntu 22.04, 2 vCPU, 8 GB + 4 GB swap) |
| Frontend | https://ia-juridica-pe.vercel.app (proyecto Vercel `bktmtjv-projects/ia-juridica-pe`) |
| API pública | https://api.68-211-120-105.sslip.io (`/health`, `/ready`) |
| Repo en la VM | `/opt/ia-juridica` (rama `v8`) |
| Secretos | `/etc/ia-juridica/compose.env`, `/etc/ia-juridica/backend.env` (root:docker, 640) |
| Datos del backend | `/srv/ia-juridica/{data,logs,temp}` |

`sslip.io` resuelve `api.68-211-120-105.sslip.io` a la IP, y Caddy saca el certificado
de Let's Encrypt solo. Si cambia la IP pública (no debería: es estática) o usas un
dominio propio, cambia `API_DOMAIN` en `compose.env` y `BACKEND_URL` en Vercel.

## 1. Frontend en Vercel

1. vercel.com → **Add New → Project** → importa el repo de GitHub.
2. **Root Directory:** `frontend`. Framework: Next.js (autodetectado). Rama de producción: `v8`
   (Settings → Environments → Production → Branch Tracking).
3. **Environment Variables** (Production y Preview):

   | Nombre | Valor |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `/api` |
   | `BACKEND_URL` | `https://api.68-211-120-105.sslip.io` |

   `NEXT_PUBLIC_API_URL` se incrusta en el build: si la cambias, redeploy.
4. Deploy. URL de producción: `https://ia-juridica-pe.vercel.app`. Redeploy manual desde `frontend/`:
   `vercel deploy --prod --yes --scope bktmtjv-projects`
5. En la VM, apunta el backend a esa URL:

   ```bash
   ssh -i ~/.ssh/vm-ia-juridica.pem azureuser@68.211.120.105
   cd /opt/ia-juridica
   sudo FRONTEND_URL=https://ia-juridica-pe.vercel.app bash deploy/azure/set-frontend.sh
   ```

A partir de ahí cada push a `v8` redeploya el frontend en Vercel automáticamente.

### Login con Google (opcional)

1. Google Cloud Console → Credentials → tu OAuth client → **Authorized redirect URIs**:
   `https://ia-juridica-pe.vercel.app/api/auth/google/callback`
2. En la VM:
   ```bash
   sudo FRONTEND_URL=https://ia-juridica-pe.vercel.app GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... \
     bash deploy/azure/set-frontend.sh
   ```

## 2. CI/CD del backend (GitHub Actions + runner en la VM)

`.github/workflows/deploy-azure.yml` corre en cada push a `v8` (salvo cambios solo en
`frontend/`, `pitch/` o `.md`) y ejecuta `deploy/azure/deploy.sh`: build, `up -d` y espera a
`/ready`. El runner vive en la VM, así que GitHub no necesita entrar por SSH.

Instalación (una vez; requiere admin del repo):

1. GitHub → repo → **Settings → Actions → Runners → New self-hosted runner** → Linux x64.
   Copia el token del comando `./config.sh`.
2. En la VM:
   ```bash
   mkdir -p ~/actions-runner && cd ~/actions-runner
   # Usa la URL/versión exacta que muestra GitHub en ese mismo paso:
   curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/v<VERSION>/actions-runner-linux-x64-<VERSION>.tar.gz
   tar xzf runner.tar.gz
   ./config.sh --url https://github.com/<owner>/IA_juridica --token <TOKEN> \
     --name vm-ia-juridica --labels azure-vm --unattended
   sudo ./svc.sh install azureuser && sudo ./svc.sh start
   ```
3. **Seguridad (repo público):** Settings → Actions → General → *Fork pull request workflows*
   → **Require approval for all external contributors**. Un PR de un fork podría, si no,
   ejecutar código en el runner de la VM.

El runner hace checkout en `~/actions-runner/_work/...` y levanta el mismo proyecto
Compose (`iajuridica`), así que reutiliza volúmenes y secretos. `/opt/ia-juridica` queda
como copia para deploys manuales.

Deploy manual: `cd /opt/ia-juridica && git pull && bash deploy/azure/deploy.sh`

## 3. Operación

```bash
C="docker compose -f deploy/azure/compose.yml --env-file /etc/ia-juridica/compose.env"
$C ps
$C logs -f --tail=100 backend
$C restart backend
docker stats --no-stream
# Backup manual de Postgres (guárdalo fuera de la VM)
$C exec -T postgres pg_dump -U juridica_user juridica_db | gzip > backup-$(date +%F).sql.gz
```

Backup automático: `deploy/azure/backup.sh` corre a las 04:00 (cron de `azureuser`) y
deja 7 días de dumps en `/srv/ia-juridica/backups`. Instalación:
`(crontab -l 2>/dev/null; echo "0 4 * * * /opt/ia-juridica/deploy/azure/backup.sh") | crontab -`

Rol admin (panel `/calidad/admin`) para una cuenta de Google:

```bash
$C exec -T postgres psql -U juridica_user -d juridica_db -c "
INSERT INTO auth_schema.user_roles (user_id, role_id, assigned_by)
SELECT u.id, r.id, u.id FROM auth_schema.users u, auth_schema.roles r
WHERE u.email = 'tu@gmail.com' AND r.name = 'admin' ON CONFLICT DO NOTHING;"
```

- Nunca `docker compose down -v`: borra la base de datos.
- Para ahorrar créditos: Azure → VM → **Detener** (que quede "Desasignada"). Al encenderla,
  Docker levanta todo solo (`restart: unless-stopped`).
- Rotar un secreto: edita `/etc/ia-juridica/backend.env` y `$C up -d --force-recreate backend`.
  Las contraseñas de Postgres/Redis solo se aplican sobre volúmenes nuevos.
- Rate limit por IP: Caddy confía en `X-Forwarded-For` (lo pone Vercel). Quien llame
  directo a la API puede falsearlo; aceptable para la demo.
