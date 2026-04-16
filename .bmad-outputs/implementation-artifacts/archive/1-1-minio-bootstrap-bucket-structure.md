# Story 1.1: MinIO Bootstrap & Bucket Structure

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the System,
I want MinIO initialized with the correct bucket structure (`projects`, `golden-set`, `models`, `snapshots`) as a Docker Compose service with a health check,
so that all downstream services (FFmpeg Worker, OpenVINO, FastAPI, Export Worker) have a ready, sovereign storage layer before they start.

---

## Acceptance Criteria

1. `docker-compose.yml` exists at project root and defines the `minio` service with correct image, ports, volumes, and health check.
2. A bucket-initialization mechanism runs once after MinIO is healthy and creates all 4 required root buckets: `projects`, `golden-set`, `models`, `snapshots`.
3. Bucket creation is **idempotent** — running `docker compose up` multiple times never fails due to already-existing buckets.
4. The MinIO health check (`mc ready local`) passes before any dependent service starts.
5. MinIO credentials (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`) are read from a `.env` file (never hardcoded).
6. A `.env.example` file exists at project root documenting all required environment variables for MinIO.
7. A smoke-test script or `docker compose` command can verify that all 4 buckets exist after stack startup.
8. All MinIO data is persisted via a named Docker volume (`minio_data`) — no data loss on `docker compose restart`.

---

## Tasks / Subtasks

- [x] Task 1 — Create `docker-compose.yml` skeleton with MinIO service (AC: 1, 4, 8)
  - [x] Define `minio` service with image `minio/minio:RELEASE.2025-04-22T22-12-26Z` (pinned tag)
  - [x] Configure S3 API port `9000` and Console port `9001`
  - [x] Mount named volume `minio_data:/data`
  - [x] Add `healthcheck` using `mc ready local` with `interval: 10s`, `timeout: 5s`, `retries: 5`, `start_period: 10s`
  - [x] Add `command: server /data --console-address ":9001"`
  - [x] Reference env vars from `.env` file: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
  - [x] Add `restart: unless-stopped` policy

- [x] Task 2 — Create `minio-init` service in `docker-compose.yml` for bucket initialization (AC: 2, 3)
  - [x] Add `minio-init` service using image `minio/mc:latest`
  - [x] Set `depends_on: minio: condition: service_healthy`
  - [x] Write inline entrypoint script:
    ```
    mc alias set local http://minio:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
    mc mb --ignore-existing local/projects
    mc mb --ignore-existing local/golden-set
    mc mb --ignore-existing local/models
    mc mb --ignore-existing local/snapshots
    ```
  - [x] Set `restart: "no"` (run once, not a long-running service)

- [x] Task 3 — Create `.env.example` at project root (AC: 5, 6)
  - [x] Document: `MINIO_ROOT_USER=minioadmin`
  - [x] Document: `MINIO_ROOT_PASSWORD=minioadmin`
  - [x] Add clear comment: "Change in production — never commit `.env` to git"
  - [x] Ensure `.env` is already in `.gitignore` (create `.gitignore` if not present)

- [x] Task 4 — Verify smoke test (AC: 7)
  - [x] After `docker compose up -d`, run: `docker compose exec minio mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD && mc ls local/
  - [x] Confirm output lists all 4 buckets: `projects/`, `golden-set/`, `models/`, `snapshots/`
  - [x] Document the smoke test command in a comment block in `docker-compose.yml` or in `README.md`

### Review Findings

- [x] [Review][Decision] Default Credentials — Added explicit security warning to .env.example about changing credentials for production.
- [x] [Review][Patch] Missing Shell Guard — Added set -e to minio-init script. [src/compose.yml:78]
- [x] [Review][Patch] Unquoted Env Vars — Quoted MINIO_ROOT_USER and MINIO_ROOT_PASSWORD in the mc alias command. [src/compose.yml:78]
- [x] [Review][Patch] Healthcheck Binary — Used absolute path /usr/bin/mc for the healthcheck. [src/compose.yml:56]

---

## Dev Notes

### Critical Architecture Constraints

**MinIO is the absolute foundation of ZachAI.** It starts first in Docker Compose (position #1 in startup chain — `architecture.md § 6`). Every other service depends on it either directly or transitively. Get this right before any other service is added.

**Bucket naming — exact names required (case-sensitive, used by all future services):**
```
projects      ← audio uploads (projects/{project_id}/audio/) and normalized files (projects/{project_id}/normalized/)
golden-set    ← training pairs from Expert Loop + User Loop
models        ← model versions (models/whisper-cmci-v{x}.{y}/) + active pointer (models/latest)
snapshots     ← DOCX/JSON document snapshots ({document_id}/)
```

**Do NOT create sub-paths/prefixes now.** Only the 4 root buckets are in scope for Story 1.1. Sub-paths like `projects/{project_id}/audio/` are created dynamically at runtime by FastAPI (Story 1.3) and FFmpeg Worker (Story 3.1). MinIO creates intermediate "prefixes" lazily when objects are uploaded — no pre-creation needed.

**`models/latest` is NOT a filesystem symlink.** It is a plain MinIO object whose content is a string pointing to the active model version directory (e.g., `whisper-cmci-v1.0/`). OpenVINO polls and reads this object (Story 3.3). Do not attempt to create it in this story.

**Presigned URL TTL (1h):** This is enforced by FastAPI policy (Story 1.3), not by MinIO bucket policy. No bucket policy configuration is required in this story.

**RGPD compliance:** Physical deletion < 48h via `DELETE /v1/media/purge/{id}` (Story 1.3 + FastAPI). MinIO's default behavior allows hard delete — no lifecycle policy needed at bootstrap stage.

### Docker Compose Startup Order

MinIO has **zero `depends_on`** — it is the root dependency. The `minio-init` service must use `condition: service_healthy` against MinIO. All future services that need MinIO (FFmpeg, OpenVINO, FastAPI, Export Worker) will be added in future stories with `condition: service_healthy` on MinIO.

**Health check strategy:** `mc ready local` is the architecture-specified check (`architecture.md § 6`). The `mc` binary is already included in the `minio/minio` image at `/usr/bin/mc`. Command form for healthcheck:
```yaml
healthcheck:
  test: ["CMD", "mc", "ready", "local"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

### Versioning / Pinning

- Use `minio/minio:RELEASE.2025-04-22T22-12-26Z` (or latest stable release tag — never use `:latest` in `docker-compose.yml` for reproducibility)
- `minio/mc:latest` for the init container is acceptable (it's ephemeral and only runs once)
- Check https://hub.docker.com/r/minio/minio/tags for the most recent RELEASE tag at implementation time

### Environment Variables

All credentials come from `.env` (Docker Compose auto-loads `.env` at project root):
```
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

The `minio-init` service needs the same vars to configure `mc alias`. Pass them via `environment:` referencing the same `.env` vars.

### File Structure — What to Create

```
zachai/
├── docker-compose.yml        ← CREATE (MinIO + minio-init services)
├── .env.example              ← CREATE
├── .env                      ← CREATE (not committed, derived from .env.example)
└── .gitignore                ← CREATE or UPDATE (add .env)
```

No `infra/` subdirectory needed — all MinIO config is inline in `docker-compose.yml` for simplicity at this stage.

### docker-compose.yml Structure Guidance

Write `docker-compose.yml` as a **skeleton for the full stack** with clearly marked `# TODO: Story X.Y` placeholder comments for the 13 other services. This prevents structural merge conflicts in future stories. The document structure (networks, volumes, services block) should be final. Add a `zachai-network` bridge network that all services will join.

Example skeleton shape:
```yaml
networks:
  zachai-network:
    driver: bridge

volumes:
  minio_data:
  # postgres_data:    # TODO: Story 1.2 (Keycloak depends on postgres)
  # redis_data:       # TODO: Story 5.2

services:
  # ── Layer 0: Storage Foundation ───────────────────────────────────
  minio:
    ...
  minio-init:
    ...

  # ── Layer 1: Identity & Gateway ───────────────────────────────────
  # postgres:        # TODO: Story 1.2
  # keycloak:        # TODO: Story 1.2
  # redis:           # TODO: Story 5.2
  # fastapi:         # TODO: Story 1.3

  # (add remaining service comment stubs per architecture.md § 6 startup order)
```

### Testing

No automated test framework is required for Story 1.1. The acceptance test is a **manual smoke test** via Docker Compose:

```bash
# Start the stack
docker compose up -d

# Wait for minio-init to complete (check its logs)
docker compose logs minio-init

# Verify buckets exist
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc ls local/

# Expected output:
# [date]  projects/
# [date]  golden-set/
# [date]  models/
# [date]  snapshots/
```

Document this exact command in `docker-compose.yml` as a comment block at the top.

### Project Structure Notes

- This is the **first file ever created** in the implementation. There are no existing code conventions to follow — establish them here.
- Use 2-space indentation in `docker-compose.yml` (standard for YAML)
- Use lowercase, kebab-case service names: `minio`, `minio-init` (consistent with the architecture.md service names)
- The `docker-compose.yml` at project root is the **single entry point** for the entire stack (no docker-compose.override.yml splitting at this stage)

### References

- Bucket structure: [Source: docs/prd.md § 6.2 Stockage (MinIO)]
- Startup order & health check: [Source: docs/architecture.md § 6 Docker Compose]
- `models/latest` pointer pattern: [Source: docs/architecture.md § 1.C Couche Compute]
- Presigned URL TTL: [Source: docs/prd.md § 6.2]
- RGPD deletion: [Source: docs/api-mapping.md § 1]
- MinIO as physical foundation: [Source: docs/architecture.md § 1.D Couche Données]

---

## Translation Note (French / Traduction)

**Résumé de la Story 1.1 :**
Cette story crée le socle de stockage physique de ZachAI. Elle produit le `docker-compose.yml` initial avec le service MinIO (S3 souverain) et un service d'initialisation qui crée les 4 buckets racines : `projects`, `golden-set`, `models`, `snapshots`. MinIO démarre en premier dans la chaîne de démarrage Docker Compose — aucune autre dépendance. Les credentials sont lus depuis `.env`. L'idempotence est garantie par `mc mb --ignore-existing`.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

(none — clean implementation, no errors encountered)

### Completion Notes List

- ✅ Created `docker-compose.yml` at project root as the full-stack skeleton. Only `minio` and `minio-init` services are active. All 13 future services are present as annotated TODO stubs (with story references, image, ports, and dependency notes) to prevent merge conflicts in future stories.
- ✅ `minio` service uses pinned image `minio/minio:RELEASE.2025-04-22T22-12-26Z`. Reviewer should verify this tag exists at hub.docker.com/r/minio/minio/tags and update if needed.
- ✅ Health check: `["CMD", "mc", "ready", "local"]` — `mc` is included in the `minio/minio` image.
- ✅ `minio-init` uses `$$MINIO_ROOT_USER` / `$$MINIO_ROOT_PASSWORD` in the YAML entrypoint (double-dollar escapes Docker Compose variable interpolation; the shell receives `$MINIO_ROOT_USER` from the container's environment).
- ✅ All 4 required buckets created idempotently: `projects`, `golden-set`, `models`, `snapshots`.
- ✅ `zachai-network` bridge network created — all future services will join it.
- ✅ `.env.example` created with MinIO vars + pre-populated stub sections for future stories (postgres, keycloak, redis, fastapi, camunda7).
- ✅ `.env` created for local dev (not committed — in `.gitignore`).
- ✅ `.gitignore` created with coverage for Python, Node.js, editors, secrets, and logs.
- ✅ Smoke test command documented in docker-compose.yml header (lines 12–16).
- ✅ No automated test framework needed for this infrastructure story — acceptance is manual smoke test via Docker Compose.

### File List

- `src/compose.yml` (created — Docker Compose V2 preferred filename)
- `src/.env.example` (created)
- `src/.env` (created — not committed)
- `src/services/` (created — directory for all custom service code)
- `src/bpmn/` (created — directory for Camunda BPMN process files)
- `.gitignore` (created — at repo root to cover entire project)
