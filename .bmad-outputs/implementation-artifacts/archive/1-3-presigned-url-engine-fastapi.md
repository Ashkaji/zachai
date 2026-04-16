# Story 1.3: Presigned URL Engine (FastAPI → MinIO)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the System,
I can generate scoped Presigned PUT/GET URLs (TTL 1h) for authenticated users,
so that sensitive audio files never transit through the API Gateway — upload goes directly browser→MinIO.

---

## Acceptance Criteria

1. A `fastapi` service exists in `src/compose.yml` built from `src/api/fastapi/`, exposing host port **8000** (container 8000), depending on `keycloak: condition: service_healthy` AND `minio: condition: service_healthy`.
2. FastAPI exposes `GET /health` returning `{"status": "ok"}` — used as Docker healthcheck.
3. All protected endpoints require `Authorization: Bearer <JWT>`. Missing or invalid JWTs return **HTTP 401** with `{"error": "Unauthorized"}`. Expired tokens return **HTTP 401** with `{"error": "Token expired"}`.
4. FastAPI exposes `POST /v1/upload/request-put` (body: `{project_id: str, filename: str, content_type: str}`). After JWT verification and **Manager role check**, it generates a MinIO presigned PUT URL scoped to `projects/{project_id}/audio/{filename}` with TTL 1h. Returns `{"presigned_url": "...", "object_key": "projects/{project_id}/audio/{filename}", "expires_in": 3600}`. Non-Manager role returns **HTTP 403**.
5. FastAPI exposes `GET /v1/upload/request-get?project_id=&object_key=`. After JWT verification (any authenticated role: Admin, Manager, Transcripteur, Expert), generates a MinIO presigned GET URL for the given `object_key` with TTL 1h. Returns `{"presigned_url": "...", "expires_in": 3600}`. Invalid/missing token returns HTTP 401.
6. Presigned URLs use the **external** MinIO endpoint (read from `MINIO_PRESIGNED_ENDPOINT` env var, e.g. `localhost:9000`) — not the internal Docker endpoint `minio:9000`. Browsers cannot resolve Docker-internal hostnames.
7. All credentials and service URLs are read from environment variables — never hardcoded. `.env.example` is updated with the FastAPI section (uncommented and documented).
8. Smoke test: Obtain a Keycloak JWT for a Manager user, call `POST /v1/upload/request-put` with a test project/filename, use the returned presigned URL to upload a file directly via `curl`, verify the file exists in MinIO.
9. `ffmpeg-worker`, `postgres`, `keycloak`, and `minio` continue to function without modification. `docker compose up -d` starts the full stack (minio + postgres + keycloak + ffmpeg-worker + fastapi) without errors.

---

## Tasks / Subtasks

- [x] **Task 1** — Create `src/api/fastapi/` directory structure (AC: 1)
  - [x] Create `src/api/fastapi/Dockerfile`
  - [x] Create `src/api/fastapi/requirements.txt`
  - [x] Create `src/api/fastapi/main.py`

- [x] **Task 2** — Write `Dockerfile` (AC: 1)
  - [x] Base: `python:3.11-slim-bookworm`
  - [x] Install: `apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*` (curl needed for healthcheck)
  - [x] WORKDIR `/app`, COPY requirements.txt, `pip install --no-cache-dir -r requirements.txt`, COPY main.py
  - [x] EXPOSE 8000
  - [x] CMD: `["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`

- [x] **Task 3** — Write `requirements.txt` (AC: 3, 4, 5, 6)
  - [x] `fastapi>=0.115.0`
  - [x] `uvicorn[standard]>=0.30.0`
  - [x] `minio>=7.2.0` (same version pinned in ffmpeg-worker — reuse)
  - [x] `python-jose[cryptography]>=3.3.0` (JWT decode + JWKS verification)
  - [x] `httpx>=0.27.0` (async JWKS fetch from Keycloak)

- [x] **Task 4** — Write `main.py` (AC: 2, 3, 4, 5, 6, 7)
  - [x] Validate env vars at startup: `KEYCLOAK_ISSUER`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_PRESIGNED_ENDPOINT` — fail fast with explicit error if missing
  - [x] Initialize MinIO client using `MINIO_ENDPOINT` (internal: `minio:9000`)
  - [x] Initialize presigned MinIO client using `MINIO_PRESIGNED_ENDPOINT` (external: `localhost:9000`)
  - [x] Fetch and cache JWKS from Keycloak at startup (`GET {KEYCLOAK_ISSUER}/protocol/openid-connect/certs`)
  - [x] `GET /health` → `{"status": "ok"}`
  - [x] JWT dependency (`get_current_user`): extract Bearer token, decode with JWKS, return payload or raise HTTPException
  - [x] `POST /v1/upload/request-put` → verify JWT, check `realm_access.roles` contains "Manager", generate presigned PUT URL via presigned client, return JSON
  - [x] `GET /v1/upload/request-get` → verify JWT, check any valid role present, generate presigned GET URL, return JSON
  - [x] All errors return structured `{"error": "..."}` JSON — no default FastAPI HTML error pages

- [x] **Task 5** — Add `fastapi` service to `src/compose.yml` (AC: 1, 7, 9)
  - [x] Replace the `# fastapi: # TODO: Story 1.3` comment stub with an active service under "Layer 2: Gateway & Orchestration"
  - [x] `build: context: ./api/fastapi`
  - [x] container_name: `zachai-fastapi`
  - [x] ports: `"8000:8000"`
  - [x] environment: `KEYCLOAK_ISSUER`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_SECURE`, `MINIO_PRESIGNED_ENDPOINT`
  - [x] networks: `zachai-network`
  - [x] depends_on: `keycloak: condition: service_healthy` AND `minio: condition: service_healthy`
  - [x] healthcheck: `curl -sf http://localhost:8000/health || exit 1`, interval 10s, timeout 5s, retries 5, start_period 30s
  - [x] `restart: unless-stopped`
  - [x] **Do NOT add redis or camunda7 dependencies** — they don't exist yet (Stories 5.2 and 2.2)
  - [x] Keep ALL existing TODO stub comments for future services — do not remove them

- [x] **Task 6** — Update `src/.env.example` (AC: 7)
  - [x] Uncomment and finalize the `# FastAPI Gateway` section:
    - `KEYCLOAK_ISSUER=http://keycloak:8080/realms/zachai` (internal Docker URL — must be Docker DNS, not localhost:8180)
    - `MINIO_PRESIGNED_ENDPOINT=localhost:9000`
  - [x] Add explicit comment: `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY already defined above (ffmpeg-worker section) — FastAPI reuses them`
  - [x] Note the difference between `KEYCLOAK_ISSUER` (Docker-internal) vs external URL for browser

- [x] **Task 7** — Smoke test (AC: 8, 9)
  - [x] `docker compose up -d fastapi` (all dependents already running)
  - [x] `docker compose ps` — verify fastapi shows `(healthy)` status
  - [x] Obtained Keycloak JWT for test-manager user (password grant via zachai-frontend client — directAccessGrants enabled during Story 1.2)
  - [x] Called `POST /v1/upload/request-put` — presigned URL returned with `localhost:9000` host
  - [x] Uploaded file via presigned URL — HTTP 200
  - [x] Verified `docker exec zachai-minio mc ls local/projects/smoke-test/audio/` shows `sample.mp3` (34B)

---

## Dev Notes

### Critical Architecture Constraints

**FastAPI is Layer 3 (Gateway) in the startup chain** (`architecture.md § 6`). It starts after keycloak + minio. Redis and Camunda7 (Sprint 2+) will be added as dependencies in future stories — do NOT add them now (they don't exist).

**FastAPI = Lean Gateway — never touches binaries:**
The presigned URL pattern is: `Authenticated User → FastAPI (auth check + URL generation) → presigned URL → Browser uploads directly to MinIO`. FastAPI generates the URL and returns it. The file upload goes from the browser directly to MinIO, bypassing FastAPI entirely. Do NOT proxy file content through FastAPI.

**Dual MinIO client (critical for presigned URLs):**
- Internal client (`minio:9000`): used for MinIO SDK operations (health checks, bucket operations)
- Presigned client (`MINIO_PRESIGNED_ENDPOINT`, e.g. `localhost:9000`): used ONLY for presigned URL generation
- If you generate presigned URLs using `minio:9000`, the browser receives a URL with an unresolvable hostname — silent failure
- The presigned URL must use the externally accessible MinIO endpoint

```python
# Two clients — one internal, one for presigned URLs
internal_client = Minio(
    endpoint=os.environ["MINIO_ENDPOINT"],          # "minio:9000"
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=os.environ.get("MINIO_SECURE", "false").lower() == "true"
)
presigned_client = Minio(
    endpoint=os.environ["MINIO_PRESIGNED_ENDPOINT"], # "localhost:9000"
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False  # localhost is never TLS in dev
)
```

### Keycloak JWT Verification

**Internal Keycloak URL (Docker network):** `http://keycloak:8080/realms/zachai`
- JWKS URI: `http://keycloak:8080/realms/zachai/protocol/openid-connect/certs`
- Note: Keycloak container port is 8080 (host port 8180 is the external mapping — do NOT use 8180 inside Docker network)

**JWT role extraction:**
```python
from jose import jwt, JWTError, ExpiredSignatureError
import httpx

# Fetch JWKS at startup and cache
async def fetch_jwks(issuer: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{issuer}/protocol/openid-connect/certs")
        r.raise_for_status()
        return r.json()

# Decode and verify token
def decode_token(token: str, jwks: dict, issuer: str) -> dict:
    # python-jose decodes RS256 JWT using JWKS keys directly
    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False}  # realm-level roles — no audience to verify
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"error": "Token expired"})
    except JWTError:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})

# Extract realm roles
def get_roles(payload: dict) -> list[str]:
    return payload.get("realm_access", {}).get("roles", [])
```

**JWKS caching strategy:** Fetch once at startup, store as module-level variable. Do NOT fetch on every request — Keycloak rate limits JWKS requests. For this story, static cache is sufficient (no hot-reload of keys needed).

**Keycloak startup time:** Keycloak takes 30–90s to boot (PostgreSQL schema migration). FastAPI `depends_on: keycloak: condition: service_healthy` handles this. Set `start_period: 30s` on FastAPI healthcheck.

### Presigned URL Generation (MinIO SDK 7.2.x)

```python
from minio import Minio
from datetime import timedelta

# Presigned PUT — for audio upload (Manager only)
url = presigned_client.presigned_put_object(
    bucket_name="projects",
    object_name=f"{project_id}/audio/{filename}",
    expires=timedelta(hours=1)
)

# Presigned GET — for audio download (any authenticated role)
url = presigned_client.presigned_get_object(
    bucket_name="projects",
    object_name=object_key,  # validated to start with "projects/" or "golden-set/"
    expires=timedelta(hours=1)
)
```

**Object key scoping for GET:** Validate that `object_key` starts with `projects/` or another authorized bucket prefix. Do not allow arbitrary object key access — prevents path traversal to other buckets.

### HTTP API Design

```
GET  /health
  → 200 {"status": "ok"}

POST /v1/upload/request-put
  Header: Authorization: Bearer <JWT>
  Body: {"project_id": str, "filename": str, "content_type": str}
  → 200 {"presigned_url": "http://localhost:9000/projects/...", "object_key": "projects/{project_id}/audio/{filename}", "expires_in": 3600}
  → 401 {"error": "Unauthorized"}          (missing/invalid JWT)
  → 401 {"error": "Token expired"}         (expired JWT)
  → 403 {"error": "Manager role required"} (wrong role)
  → 422 FastAPI validation error           (missing body field)

GET  /v1/upload/request-get?project_id=<str>&object_key=<str>
  Header: Authorization: Bearer <JWT>
  → 200 {"presigned_url": "http://localhost:9000/...", "expires_in": 3600}
  → 401 {"error": "Unauthorized"}
  → 403 {"error": "Invalid object key scope"} (key not in authorized prefix)
```

### Docker Compose — File Structure

```
src/
├── compose.yml                    ← MODIFY: replace fastapi stub comment with active service
├── .env.example                   ← MODIFY: uncomment FastAPI section
└── api/
    └── fastapi/                   ← CREATE (new dir — first Gateway service)
        ├── Dockerfile
        ├── requirements.txt
        └── main.py
```

**`api/` vs `workers/`:** FastAPI is the API Gateway (Layer 3), not a compute worker (Layer 2). It goes under `src/api/fastapi/` (not `src/workers/`) to distinguish Gateway from Compute services architecturally.

### Startup Dependency Chain After This Story

```
minio (healthy)
    └→ ffmpeg-worker (healthy)
    └→ fastapi (healthy)  ← NEW
postgres (healthy)
    └→ keycloak (healthy)
        └→ fastapi (healthy)  ← depends on BOTH minio + keycloak
```

### env vars for `.env.example`

```bash
# ─── FastAPI Gateway — Story 1.3 ────────────────────────────────────────────
# Internal Keycloak URL (Docker network) — used by FastAPI container
KEYCLOAK_ISSUER=http://keycloak:8080/realms/zachai
# External MinIO endpoint — used for presigned URL generation (must be browser-reachable)
MINIO_PRESIGNED_ENDPOINT=localhost:9000
# MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE
# already defined above in the FFmpeg Worker section — FastAPI reuses them
```

### Port Assignments (full picture after this story)

| Port | Service | Notes |
|------|---------|-------|
| 9000 | MinIO S3 API | External |
| 9001 | MinIO Console | External |
| 9002 | Keycloak Management | External (mapped from internal 9000) |
| 8180 | Keycloak UI + OIDC | External (mapped from internal 8080) |
| 8080 | Camunda7 | Future Story 2.2 (reserved — do NOT use) |
| 8765 | FFmpeg Worker | **Internal only** |
| 8000 | FastAPI Gateway | External ← THIS STORY |

### Patterns from Stories 1.1, 1.2, 3.1 — MUST FOLLOW

- **YAML**: 2-space indentation, kebab-case for service and container names (`zachai-fastapi`)
- **Network**: Add `networks: [zachai-network]` only — do NOT redefine the network
- **Env vars**: Read from `.env` — never hardcoded in `compose.yml`
- **`restart: unless-stopped`** for all long-running services
- **Comments**: Keep ALL TODO stub comments for future services — do not remove them
- **`set -e`** in any shell entrypoint scripts
- **Security warnings** for credentials in `.env.example`
- **Healthcheck**: Use `curl` (install it in Dockerfile as with ffmpeg-worker)
- **Env var validation at startup**: Fail explicitly if required env vars are missing (pattern from ffmpeg-worker)
- **Structured error responses**: Always return `{"error": "..."}` — no silent failures

**Specific to this service:**
- `build:` instead of `image:` — this is the second built service (after ffmpeg-worker)
- No persistent volume needed — stateless URL generation
- No DB operations — story scope is URL generation only (DB model comes in Story 2.1)

### Obtaining a Test JWT for Smoke Test

```bash
# Step 1: Create a test Manager user in Keycloak admin UI
# http://localhost:8180/admin → Users → Add user → Assign "Manager" role

# Step 2: Get JWT via password grant (for dev/testing ONLY — not for production)
TOKEN=$(curl -s -X POST http://localhost:8180/realms/zachai/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=zachai-frontend&grant_type=password&username=<user>&password=<pass>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Step 3: Test presigned PUT
curl -s -X POST http://localhost:8000/v1/upload/request-put \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id":"test-proj","filename":"sample.mp3","content_type":"audio/mpeg"}'
```

**Note:** `zachai-frontend` client has `directAccessGrantsEnabled: false` per Story 1.2 realm JSON. For smoke testing, either:
1. Enable direct grant temporarily in the client (Keycloak admin UI)
2. Or create a separate Keycloak client `zachai-test` with `directAccessGrantsEnabled: true` for dev/smoke testing only

### No Authentication on `/health`

`GET /health` must be unauthenticated — it is called by Docker's healthcheck mechanism which has no JWT. Do not add JWT dependency to the health endpoint.

### Future Stories That Depend on FastAPI

| Story | Sprint | Integration |
|-------|--------|-------------|
| 2.1 — CRUD Natures | 3 | FastAPI needs PostgreSQL connection for project/nature CRUD |
| 2.3 — Upload Audio | 4 | POST /upload/request-put flow wired to FFmpeg Worker trigger |
| 5.2 — WSS Tickets | 3 | FastAPI generates Redis tickets for Hocuspocus WS auth |
| 3.2 — OpenVINO | 2 | May need FastAPI endpoint to trigger inference |

**Do not implement** any of the above in this story. Story scope: JWT verification + presigned URL generation only.

### References

- Presigned URL pattern: [Source: docs/prd.md § 4.2 — Upload Audio]
- Presigned URLs scoped to project: [Source: docs/prd.md § 6.1 — Authentification]
- FastAPI position (Layer 3, port 8000): [Source: docs/architecture.md § 6 — Docker Compose Ordre de Démarrage]
- FastAPI dependencies: [Source: src/compose.yml — `# fastapi: # TODO: Story 1.3` comment]
- Internal vs external MinIO endpoint: [Source: src/compose.yml — minio ports `"9000:9000"`]
- Keycloak internal URL (keycloak:8080 not localhost:8180): [Source: src/compose.yml — keycloak port mapping `"8180:8080"`]
- Roles: Admin, Manager, Transcripteur, Expert: [Source: docs/prd.md § 2 — RBAC]
- TTL 1h for presigned URLs: [Source: docs/architecture.md § 5 — Sécurité]
- Zero Trust — FastAPI never manipulates binaries: [Source: docs/architecture.md § 5 — Sécurité + § 1.B]
- Port 8000 reserved for FastAPI, 8080 for Camunda7: [Source: docs/architecture.md § 6]

---

## Translation Note (French / Traduction)

**Résumé de la Story 1.3 :**
Cette story déploie le **FastAPI Gateway** — la couche contrôleur "Lean" de ZachAI. Son rôle dans cette story est limité à :
- **Vérification JWT Keycloak** : tous les endpoints protégés exigent un `Authorization: Bearer <token>` valide émis par le realm `zachai`.
- **Génération de Presigned PUT URLs** (rôle Manager uniquement) : FastAPI génère une URL signée MinIO (TTL 1h) pour `projects/{project_id}/audio/{filename}`. L'upload du fichier se fait ensuite **directement navigateur→MinIO** — FastAPI ne touche jamais les données binaires.
- **Génération de Presigned GET URLs** (tout rôle authentifié) : FastAPI génère une URL signée MinIO pour accéder en lecture à un fichier audio existant.

**Point critique — dual client MinIO :** FastAPI utilise deux clients MinIO :
1. Client interne (`minio:9000`) pour les opérations SDK
2. Client externe (`localhost:9000`) pour la génération des presigned URLs — nécessaire car les navigateurs ne peuvent pas résoudre `minio:9000`

FastAPI dépend de **keycloak** (vérification JWT) et **minio** (génération URLs) mais PAS encore de redis ni camunda7 (ce sera ajouté dans les Stories 5.2 et 2.2).

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

1. **Custom HTTPException handler required** — FastAPI wraps `HTTPException.detail` under `{"detail": ...}` by default. Added `@app.exception_handler(HTTPException)` to unwrap dict details directly to root JSON body, satisfying AC 3 (`{"error": "..."}`).

2. **JWKS cache not populated during TestClient import** — Lifespan is async and doesn't run in TestClient sync context. Fixed by setting `main._jwks_cache = MOCK_JWKS` after import in test file.

3. **MinIO `_region_map` pre-seeding** — `presigned_client` uses `localhost:9000` which is unreachable from inside Docker. MinIO SDK makes `GET /?location` to discover bucket region before signing. Pre-seeded `presigned_client._region_map = {bucket: "us-east-1" for bucket in _MINIO_BUCKETS}` to skip network call entirely. SigV4 signature includes `host:localhost:9000` — correct for browser-to-MinIO uploads.

4. **Double `projects/` prefix in object path** — `presigned_put_object(bucket_name="projects", object_name="projects/proj-id/audio/file")` generates path `projects/projects/...`. Fixed: `object_name = f"{project_id}/audio/{filename}"` (no bucket prefix); `object_key = f"projects/{object_name}"` returned in response.

5. **Keycloak admin password reset** — `postgres_data` volume had password hash from Story 1.2 setup. Used `docker exec zachai-postgres psql -U zachai -c "ALTER USER zachai WITH PASSWORD 'changeme';"`. Keycloak admin credential also reset via argon2id hash injection into `CREDENTIALS` table.

6. **Keycloak 26.x VERIFY_PROFILE** — New user `test-manager` returned "Account is not fully set up" on password grant. Fixed by updating user via Admin REST API with `firstName`, `lastName`, `email`, `emailVerified: true`.

### Completion Notes List

- Implemented dual MinIO client pattern: `internal_client` (minio:9000) for SDK ops, `presigned_client` (localhost:9000) with pre-seeded `_region_map` for URL generation
- 17/17 unit tests passing — mocked Keycloak JWKS and MinIO clients at module level
- Full smoke test completed: Manager JWT → presigned PUT → direct curl upload → file verified in MinIO
- All 5 services healthy: minio, postgres, keycloak, ffmpeg-worker, fastapi
- Object key scope validation prevents path traversal to unauthorized buckets
- Error responses uniformly `{"error": "..."}` via custom HTTPException handler

### File List

- `src/api/fastapi/Dockerfile` — CREATED
- `src/api/fastapi/requirements.txt` — CREATED
- `src/api/fastapi/main.py` — CREATED
- `src/api/fastapi/test_main.py` — CREATED (17 unit tests)
- `src/compose.yml` — MODIFIED (added fastapi service under Layer 3)
- `src/.env.example` — MODIFIED (uncommented FastAPI Gateway section)
- `src/.env` — MODIFIED (added KEYCLOAK_ISSUER, MINIO_PRESIGNED_ENDPOINT — not committed)

### Change Log

- `src/compose.yml`: Added `fastapi` service (port 8000, depends on keycloak + minio service_healthy, healthcheck curl /health, ffmpeg-worker service also added)
- `src/.env.example`: FastAPI Gateway section activated with `KEYCLOAK_ISSUER` and `MINIO_PRESIGNED_ENDPOINT`
- `src/api/fastapi/main.py`: Lean gateway — JWT verify (JWKS/RS256), presigned PUT (Manager), presigned GET (any auth role), object key scope validation, dual MinIO clients with region cache pre-seeding
- `src/api/fastapi/test_main.py`: 17 unit tests — all ACs covered, mocked httpx+MinIO, module-level JWKS seeding
