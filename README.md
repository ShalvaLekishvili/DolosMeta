# DolosMeta

DolosMeta is a universal file metadata and forensic-inspection web application. The repository contains a Next.js frontend and a native Python/FastAPI analysis engine.

## Architecture

- **Frontend:** Next.js App Router + React + TypeScript
- **Analyzer API:** FastAPI + native Python parsers
- **Local development:** frontend on `http://127.0.0.1:3000`, API on `http://127.0.0.1:8000`
- **Production frontend:** prepared for Netlify
- **Production backend:** prepared for Render with automatic Docker startup, health checks, restart handling, and Git-based auto-deploy

### Why the backend is separate from Netlify

The current analyzer stores active analysis records in process memory and keeps uploaded files temporarily on disk so later requests can retrieve metadata sections, hex ranges, and cleaned files. That lifecycle is intentionally stateful. A short-lived/stateless function runtime is therefore not a safe drop-in replacement for the existing FastAPI service.

Netlify should host the Next.js frontend. The FastAPI service should run on a persistent/container host using the included `Dockerfile.backend`.

## Requirements

- Node.js 22
- npm
- Python 3.9+ (3.12 recommended)
- Docker / Docker Compose (optional)

## Local setup

```bash
cp .env.example .env.local
make install
make dev
```

The UI will use the local API automatically in development.

## Frontend validation

```bash
npm install
npm run typecheck
npm run lint
npm run build
```

## Backend validation

```bash
make install-backend
make test-backend
make lint-backend
```

## Docker

Run the complete local stack with:

```bash
docker compose up --build
```

By default the frontend is exposed on `127.0.0.1:8080` and the backend on `127.0.0.1:8000`.

## Deploy the backend to Render — automatic startup

The repository includes a root-level `render.yaml` Blueprint. After this branch is merged to `main`, the backend can be created without manually entering a Python start command.

1. Open Render and choose **New → Blueprint**.
2. Connect the `ShalvaLekishvili/DolosMeta` GitHub repository.
3. Render reads `render.yaml` and creates the `dolosmeta-api` Docker web service.
4. When Render asks for `CORS_ORIGINS`, enter the exact Netlify production origin, for example:

   ```text
   https://your-site.netlify.app
   ```

   Multiple allowed origins can be comma-separated.
5. Apply the Blueprint.
6. Render builds `Dockerfile.backend` and starts the API automatically.
7. Verify:

   ```text
   https://YOUR-RENDER-SERVICE.onrender.com/api/v1/health
   ```

   Expected response:

   ```json
   {"status":"ok","service":"DolosMeta"}
   ```

### Automatic backend behavior

The Render configuration is intentionally hands-off after the first setup:

- Docker starts `uvicorn` automatically when a deployment boots.
- The server binds to Render's runtime-provided `PORT` automatically, with `8000` as a local fallback.
- `/api/v1/health` is configured as the Render health check.
- Render can restart an unhealthy service instance.
- `autoDeployTrigger: checksPass` deploys new `main` commits only after GitHub CI checks pass.
- GitHub CI builds the backend Docker image, starts it, and calls `/api/v1/health` as a smoke test.

The Blueprint currently uses Render's `free` web-service plan. Free Render services can spin down after inactivity and wake automatically on the next request. For a continuously warm production API, change the Render instance type to a paid always-on instance.

## Deploy the frontend to Netlify

1. Import this GitHub repository into Netlify.
2. Use Node.js 22. The repository's `netlify.toml` already sets it.
3. Netlify should use the repository build command: `npm run build`.
4. Do **not** set a custom `dist/client` publish directory. The project uses the normal Next.js build output and Netlify's Next.js runtime integration.
5. Deploy the FastAPI backend to Render first and copy its public HTTPS URL.
6. In **Netlify → Site configuration → Environment variables**, add:

   ```text
   NEXT_PUBLIC_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
   ```

7. Trigger a new Netlify deploy after changing `NEXT_PUBLIC_API_BASE_URL` because it is a public build-time Next.js variable.
8. Ensure the backend's `CORS_ORIGINS` contains the exact Netlify production URL and any custom domain you intentionally support.

### Optional site URL override

Netlify's deployment URL is detected automatically for metadata generation. If you later attach a custom domain, you can explicitly set:

```text
NEXT_PUBLIC_SITE_URL=https://meta.example.com
```

## Production environment variables

### Frontend

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Yes for analysis | Public HTTPS URL of the FastAPI backend |
| `NEXT_PUBLIC_SITE_URL` | Optional | Canonical frontend URL; Netlify URL is otherwise detected automatically |

### Backend

| Variable | Typical production value |
| --- | --- |
| `APP_ENV` | `production` |
| `CORS_ORIGINS` | Exact Netlify/custom-domain origins |
| `TEMP_DIR` | `/app/data/tmp` |
| `MAX_UPLOAD_SIZE_MB` | `250` or a lower operational limit |
| `UPLOAD_RETENTION_MINUTES` | `15` |
| `MAX_ANALYSIS_SECONDS` | `45` |
| `PORT` | Supplied automatically by the hosting platform |

See `backend/dolosmeta/config.py` for the complete list of resource and parser limits.

## Security notes

- Uploaded files are written to a temporary backend directory and removed when analyses expire or the service shuts down.
- The browser sends files directly to the configured analyzer API; no third-party metadata service is required.
- Production CORS should list only trusted frontend origins. Do not use `*` for the deployed analyzer.
- Keep secrets out of `NEXT_PUBLIC_*` variables because those values are embedded in browser-delivered JavaScript.
- The repository includes defensive upload limits, parser limits, decompression limits, archive-entry limits, and restricted HTTP methods.
- Render's free filesystem is ephemeral. DolosMeta uses it only for temporary analysis files, not long-term storage.

## Important deployment behavior

A Netlify deployment can successfully serve the UI without `NEXT_PUBLIC_API_BASE_URL`, but file analysis will intentionally show a clear configuration error until a backend URL is configured. This prevents production browsers from incorrectly trying to contact their own `127.0.0.1:8000`.

On the Render Free plan, the first request after a period of inactivity can take longer because the service may need to wake. This does not require manual startup.

## Repository layout

```text
app/                  Next.js frontend
backend/dolosmeta/    FastAPI API and native metadata engine
backend/tests/        Analyzer fixtures and tests
docs/                 Architecture and parser documentation
Dockerfile            Frontend container
Dockerfile.backend    Analyzer container
docker-compose.yml    Local full-stack deployment
netlify.toml          Netlify frontend configuration
render.yaml           Render backend auto-deploy configuration
```
