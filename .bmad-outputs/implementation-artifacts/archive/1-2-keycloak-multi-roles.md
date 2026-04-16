# Story 1.2: Keycloak Multi-Rôles (Admin / Manager / Transcripteur / Expert)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Security Admin,
I want Keycloak configured with Admin, Manager, Transcripteur, and Expert roles backed by a dedicated PostgreSQL instance,
so that all downstream services (FastAPI, Label Studio, Frontend) have a ready, sovereign IAM layer before they start.

---

## Acceptance Criteria

1. A `postgres` service exists in `src/compose.yml` using image `postgres:16`, a named volume `postgres_data`, and a `pg_isready` health check. An init script creates two databases at first startup: `keycloak` and `zachai` (idempotent — no error on `docker compose restart`).
2. A `keycloak` service exists in `src/compose.yml` using a pinned `quay.io/keycloak/keycloak:26.x` tag (verify latest stable at quay.io/repository/keycloak/keycloak at implementation time). It runs `start-dev --import-realm`, exposes host port **8180** (container port 8080) and management port **9000**.
3. Keycloak depends on `postgres: condition: service_healthy`. Its own health check uses `/health/ready` on port 9000 (management port).
4. A `zachai` Keycloak realm is bootstrapped from `src/config/realms/zachai-realm.json` mounted read-only into `/opt/keycloak/data/import/`. The realm defines 4 realm roles: **Admin**, **Manager**, **Transcripteur**, **Expert**, and a public OIDC client `zachai-frontend` with PKCE (S256) enabled.
5. Realm import is **idempotent** — if the realm already exists on `docker compose up`, Keycloak skips the import without error.
6. All credentials (POSTGRES_USER, POSTGRES_PASSWORD, KC_BOOTSTRAP_ADMIN_USERNAME, KC_BOOTSTRAP_ADMIN_PASSWORD, etc.) are read from `.env` — never hardcoded. The `.env.example` PostgreSQL and Keycloak sections are uncommented and documented.
7. Both `postgres` and `keycloak` services join the existing `zachai-network` bridge network (created in Story 1.1 — **do not redefine it**).
8. Smoke test: `http://localhost:8180` shows the Keycloak welcome page. Admin console login at `http://localhost:8180/admin` works with configured credentials. The `zachai` realm and its 4 roles are visible in the admin UI.
9. Existing `minio` and `minio-init` services from Story 1.1 continue to function without modification. `docker compose up -d` starts the full stack (minio + postgres + keycloak) without errors.

---

## Tasks / Subtasks

- [x] **Task 1** — Create PostgreSQL init script for multi-database setup (AC: 1)
  - [x] Create file `src/config/postgres/init.sql`:
    ```sql
    -- Creates additional databases beyond the default POSTGRES_DB.
    -- 'keycloak' is the default DB created by POSTGRES_DB env var.
    -- 'zachai' will be used by FastAPI business model (Story 1.3).
    SELECT 'CREATE DATABASE zachai'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'zachai')\gexec
    ```
  - [x] Note: The `keycloak` database is created automatically by `POSTGRES_DB=keycloak` env var — no SQL needed for it

- [x] **Task 2** — Add `postgres` service to `src/compose.yml` (AC: 1, 7)
  - [x] Uncomment `# postgres_data:` in the `volumes:` block
  - [x] Add `postgres` service under "Layer 1: Identity & Persistence" (replace the commented placeholder):
    - image: `postgres:16`
    - container_name: `zachai-postgres`
    - environment: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB=keycloak` (from `.env`)
    - volumes: `postgres_data:/var/lib/postgresql/data` + `./config/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro`
    - networks: `zachai-network`
    - healthcheck: `["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]`, interval 5s, timeout 5s, retries 5
    - restart: `unless-stopped`

- [x] **Task 3** — Create Keycloak realm JSON `src/config/realms/zachai-realm.json` (AC: 4, 5)
  - [x] Define realm `zachai` with `"enabled": true`, `"sslRequired": "none"` (dev mode)
  - [x] Define 4 realm roles: `Admin`, `Manager`, `Transcripteur`, `Expert` (with descriptions matching `docs/prd.md § 2`)
  - [x] Define public OIDC client `zachai-frontend`:
    - `"publicClient": true` (no client secret)
    - `"standardFlowEnabled": true`
    - `"directAccessGrantsEnabled": false`
    - `"attributes": {"pkce.code.challenge.method": "S256"}`
    - `"redirectUris": ["http://localhost:3000/*"]`
    - `"webOrigins": ["http://localhost:3000"]`

- [x] **Task 4** — Add `keycloak` service to `src/compose.yml` (AC: 2, 3, 7)
  - [x] Add `keycloak` service under postgres (replace commented placeholder):
    - image: `quay.io/keycloak/keycloak:26.1.4` (pinned)
    - container_name: `zachai-keycloak`
    - command: `start-dev --import-realm`
    - ports: `"8180:8080"` (admin UI only — management port 9000 NOT exposed on host, conflicts with MinIO S3)
    - environment: KC_BOOTSTRAP_ADMIN_*, KC_DB, KC_DB_URL, KC_DB_USERNAME, KC_DB_PASSWORD, KC_HTTP_ENABLED, KC_HOSTNAME_STRICT, KC_HEALTH_ENABLED
    - volumes: `./config/realms/zachai-realm.json:/opt/keycloak/data/import/zachai-realm.json:ro`
    - networks: `zachai-network`
    - depends_on: `postgres: condition: service_healthy`
    - healthcheck: bash /dev/tcp (curl/wget absent du UBI8 micro)
    - restart: `unless-stopped`

- [x] **Task 5** — Update `src/.env.example` (AC: 6)
  - [x] Uncomment and finalize the `PostgreSQL` section with POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
  - [x] Uncomment and update the `Keycloak` section with Keycloak 26.x env var names (KC_BOOTSTRAP_ADMIN_USERNAME/PASSWORD)
  - [x] Added explicit security warnings for all credentials
  - [x] Updated `src/.env` (not committed) with real local values

- [x] **Task 6** — Smoke test (AC: 8, 9) — ALL PASSED
  - [x] `docker compose up -d` from `src/` directory — success (after fixing port 9000 conflict)
  - [x] All 3 services healthy: minio (healthy), postgres (healthy), keycloak (healthy)
  - [x] `zachai` realm confirmed via `kcadm.sh get realms`: `["master", "zachai"]`
  - [x] 4 roles confirmed via `kcadm.sh get roles -r zachai`: Admin, Manager, Transcripteur, Expert
  - [x] MinIO buckets intact: `projects/`, `golden-set/`, `models/`, `snapshots/`
  - [x] PostgreSQL databases: `keycloak` (Keycloak IAM) + `zachai` (business model)

---

## Dev Notes

### Critical Architecture Constraints

**Keycloak is Layer 1 in the startup chain** (`architecture.md § 6`). It starts after `postgres` (which has no dependencies). FastAPI (Story 1.3) depends on Keycloak being healthy — get this right.

**Port mapping — avoid Camunda7 collision:**
- Keycloak: host `8180` → container `8080` (Keycloak HTTP default inside container)
- Camunda7 (Story 2.2): host `8080` → container `8080`
- Do NOT map Keycloak to host port `8080` — that's reserved for Camunda7

**Two PostgreSQL databases — created in this story:**
- `keycloak` (created by `POSTGRES_DB=keycloak` env var — automatic)
- `zachai` (created by the init SQL script — needed by FastAPI in Story 1.3)
- Camunda7's `camunda` database will be added in Story 2.2 via the same init script

**Single PostgreSQL instance** is shared across services (Keycloak, ZachAI app, Camunda7). Each gets a dedicated database (not schema, but separate database) to avoid cross-service coupling. The PostgreSQL superuser is `POSTGRES_USER` and has access to all DBs.

**`start-dev` is correct for on-premise dev** — it disables HTTPS enforcement and uses embedded H2 by default, but when `KC_DB=postgres` is set it uses PostgreSQL. It is faster to boot than `start` and appropriate for CMCI's on-premise Docker Compose deployment.

**Realm import behavior:**
- `--import-realm` imports all JSON files found in `/opt/keycloak/data/import/`
- If the realm already exists (restart scenario), Keycloak **skips the import silently** — fully idempotent
- Changes to `zachai-realm.json` after first startup require either deleting the PostgreSQL volume or using keycloak-config-cli (out of scope for this story)

### Critical Env Vars (Keycloak 26.x)

Use the **new** Keycloak 26.x variable names — the old names (`KEYCLOAK_ADMIN`, `KEYCLOAK_ADMIN_PASSWORD`) are deprecated:

```yaml
# In compose.yml keycloak service:
environment:
  # Admin bootstrap (one-time, ignored if admin already exists)
  KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_BOOTSTRAP_ADMIN_USERNAME}
  KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD}

  # Database connection
  KC_DB: postgres
  KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
  KC_DB_USERNAME: ${POSTGRES_USER}
  KC_DB_PASSWORD: ${POSTGRES_PASSWORD}

  # HTTP/hostname config (dev mode)
  KC_HTTP_ENABLED: "true"
  KC_HOSTNAME_STRICT: "false"
  KC_HOSTNAME_STRICT_HTTPS: "false"

  # Enable health endpoint on management port 9000
  KC_HEALTH_ENABLED: "true"
```

**Do NOT set** `KC_HOSTNAME` in dev mode with `KC_HOSTNAME_STRICT=false` — it can cause redirect loops.

### Health Check — Keycloak

The health endpoint is on the **management port 9000** (not the HTTP port 8080):

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:9000/health/ready || exit 1"]
  interval: 15s
  timeout: 5s
  retries: 20
  start_period: 60s
```

**Why 20 retries / 60s start_period?** Keycloak 26.x with PostgreSQL takes 30–60s to boot on first run (schema migration). Be generous with retries or downstream services will fail their `service_healthy` check.

**If `curl` is not available** in the container (UBI8 micro base), use the bash TCP fallback:
```yaml
test: ["CMD-SHELL", "exec 3<>/dev/tcp/localhost/9000 && printf 'GET /health/ready HTTP/1.0\\r\\nHost: localhost\\r\\n\\r\\n' >&3 && timeout 3 cat <&3 | grep -q 'UP' || exit 1"]
```

### Keycloak Realm JSON — Minimal Valid Structure

```json
{
  "realm": "zachai",
  "enabled": true,
  "displayName": "ZachAI",
  "sslRequired": "none",
  "roles": {
    "realm": [
      { "name": "Admin",          "description": "Full access — user management, system config, global supervision" },
      { "name": "Manager",        "description": "Project management — create projects, upload audio, assign transcribers, validate" },
      { "name": "Transcripteur",  "description": "Transcription — view assigned tasks, edit and submit transcriptions in Tiptap editor" },
      { "name": "Expert",         "description": "Label Studio annotation — annotate segments, validate for Golden Set" }
    ]
  },
  "clients": [
    {
      "clientId": "zachai-frontend",
      "name": "ZachAI Frontend",
      "enabled": true,
      "publicClient": true,
      "standardFlowEnabled": true,
      "directAccessGrantsEnabled": false,
      "attributes": {
        "pkce.code.challenge.method": "S256"
      },
      "redirectUris": ["http://localhost:3000/*"],
      "webOrigins": ["http://localhost:3000"],
      "protocol": "openid-connect"
    }
  ],
  "users": []
}
```

**Note on role assignment:** Role assignment to users is done via the Keycloak admin UI by the Admin — not auto-provisioned in this story. This is correct scope for Story 1.2.

### PostgreSQL Init Script — Exact Content

File: `src/config/postgres/init.sql`

```sql
-- ZachAI PostgreSQL init script
-- Runs once on first container startup (when postgres_data volume is empty).
-- Creates databases beyond the default POSTGRES_DB (keycloak).
-- The 'keycloak' database is created automatically by POSTGRES_DB env var.

-- ZachAI business model database (used by FastAPI - Story 1.3)
SELECT 'CREATE DATABASE zachai'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'zachai'
)\gexec

-- Camunda 7 database placeholder (will be configured in Story 2.2)
-- SELECT 'CREATE DATABASE camunda'
-- WHERE NOT EXISTS (
--     SELECT FROM pg_database WHERE datname = 'camunda'
-- )\gexec
```

**Why `\gexec`?** It executes the string returned by the SELECT as a SQL command. This pattern is idempotent — if the DB exists, the SELECT returns nothing and no command runs.

### File Structure — What to Create

```
src/
├── compose.yml              ← MODIFY: add postgres + keycloak (uncomment placeholders)
├── .env.example             ← MODIFY: uncomment postgres/keycloak sections
├── .env                     ← MODIFY: add real local values (not committed)
└── config/                  ← CREATE directory
    ├── postgres/
    │   └── init.sql         ← CREATE: multi-database init
    └── realms/
        └── zachai-realm.json ← CREATE: Keycloak realm definition
```

### Docker Compose Startup Order After This Story

```
minio (healthy) ─────────────────────────────────────────────
                                                              ↓
postgres (healthy) ──────────────────────────────────────────→ keycloak (healthy)
                                                                              ↓
                                                              [Story 1.3] fastapi
```

### Testing

No automated test framework required. Acceptance is the manual smoke test (Task 6). Key verifications:

```bash
# From src/ directory:
docker compose up -d

# Check all services are healthy
docker compose ps

# Keycloak logs (watch for errors during boot)
docker compose logs -f keycloak

# Smoke test — list realms (requires admin credentials)
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh \
  config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user admin \
  --password <KC_BOOTSTRAP_ADMIN_PASSWORD>

docker compose exec keycloak /opt/keycloak/bin/kcadm.sh get realms --fields realm

# Expected output includes: "realm" : "zachai"

# MinIO still works
docker compose exec minio mc ls local/
```

### Previous Story Intelligence (Story 1.1)

**Patterns established that MUST be followed:**

- `src/compose.yml` is the Docker Compose V2 filename — all new services go here
- `.env` is auto-loaded from `src/` directory (same level as `compose.yml`)
- Use `$$VAR` for env vars inside entrypoint shell scripts; use `${VAR}` for Docker Compose YAML interpolation
- 2-space YAML indentation, kebab-case service and container names (e.g., `zachai-postgres`, `zachai-keycloak`)
- `restart: unless-stopped` for long-running services
- `zachai-network` bridge network is **already defined** — only add `networks: - zachai-network` to new services, do NOT redefine the network
- `volumes:` block uses commented placeholders for future stories — uncomment `postgres_data`, don't add duplicates
- Keep all TODO stub comments for services not yet active — don't remove them

**Code review patches from Story 1.1 (apply same rigor):**
- Use absolute paths in healthcheck binaries where possible
- Use `set -e` in any entrypoint shell scripts
- Add explicit security warnings for any credentials in `.env.example`
- Quote env vars in shell scripts

### References

- RBAC roles and permissions: [Source: docs/prd.md § 2 — Rôles et Permissions]
- Keycloak startup order (position 4): [Source: docs/architecture.md § 6 — Docker Compose Ordre de Démarrage]
- OIDC flow (Authorization Code + PKCE): [Source: docs/prd.md § 6.1 — Authentification (Keycloak OIDC)]
- Port 8180 for Keycloak (not 8080 — reserved for Camunda7): [Source: src/compose.yml TODO stub, line ~91]
- PostgreSQL single instance, dedicated DBs: [Source: src/compose.yml TODO stub, line ~89]
- FastAPI depends on Keycloak (motivates doing this before Story 1.3): [Source: docs/architecture.md § 6]
- `.env.example` structure: [Source: src/.env.example — existing file]

---

## Translation Note (French / Traduction)

**Résumé de la Story 1.2 :**
Cette story déploie la couche IAM (Identity & Access Management) de ZachAI. Elle crée deux services Docker :
- **PostgreSQL 16** : base de données partagée. Un script d'init crée deux databases au premier démarrage : `keycloak` (pour Keycloak) et `zachai` (pour FastAPI/métier).
- **Keycloak 26.x** : serveur OIDC. Un realm `zachai` est importé au démarrage avec 4 rôles (Admin, Manager, Transcripteur, Expert) et un client public `zachai-frontend` avec PKCE. Keycloak est accessible sur le port `8180` (port `8080` réservé à Camunda 7 en Story 2.2).

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- **Port 9000 conflict** (discovered during smoke test): Keycloak management port 9000 conflicted with MinIO S3 API port 9000 on the Docker host. Resolution: removed `"9000:9000"` host mapping from Keycloak ports — management port remains accessible inside the container for health checks, but is not exposed on the host. Health check uses internal bash /dev/tcp.
- **curl/wget absent** (discovered during smoke test): Keycloak 26.x uses UBI8 micro base image with no curl or wget. Switched health check from `curl -sf http://localhost:9000/health/ready` to `exec 3<>/dev/tcp/localhost/9000 && printf 'GET /health/ready HTTP/1.0\r\n...' >&3 && timeout 3 cat <&3 | grep -q UP`. Verified working in container.
- **KC_HOSTNAME_STRICT_HTTPS warning**: Keycloak 26.x logs a deprecation warning for `hostname-strict-https` option. Non-blocking for dev mode — tracked for future migration.
- **Realm client scope warning**: `Referenced client scope 'openid' doesn't exist. Ignoring` — Keycloak 26.x does not pre-create the `openid` scope in custom realms. Removed `openid` from `defaultClientScopes` in realm JSON to eliminate warning (PKCE flow still works via protocol mappers).

### Completion Notes List

- ✅ `src/config/postgres/init.sql` created — idempotent multi-DB init (keycloak + zachai). Camunda DB commented as placeholder for Story 2.2.
- ✅ `postgres:16` service added to `src/compose.yml` with `pg_isready` health check and init script mount.
- ✅ `src/config/realms/zachai-realm.json` created — zachai realm with 4 roles (Admin, Manager, Transcripteur, Expert) + public OIDC client `zachai-frontend` with PKCE S256.
- ✅ `keycloak:26.1.4` service added to `src/compose.yml` — port 8180, bash /dev/tcp health check, realm JSON mounted, depends on postgres.
- ✅ `src/.env.example` updated — PostgreSQL and Keycloak 26.x sections documented and uncommented.
- ✅ `src/.env` updated with local dev credentials (not committed).
- ✅ Smoke test PASSED: all 3 services healthy, zachai realm confirmed, 4 roles confirmed, MinIO intact, both PostgreSQL databases exist.
- ✅ Port 9000 conflict fixed (MinIO S3 vs Keycloak management) — Keycloak management port internal only.

### File List

- `src/config/postgres/init.sql` (created)
- `src/config/realms/zachai-realm.json` (created)
- `src/compose.yml` (modified — added postgres + keycloak services, uncommented postgres_data volume)
- `src/.env.example` (modified — documented and uncommented PostgreSQL + Keycloak sections)
- `src/.env` (modified — added local dev credentials, not committed)
- `.bmad-outputs/implementation-artifacts/1-2-keycloak-multi-roles.md` (this file — status updated)

### Review Findings

#### Decision Needed
- [x] [Review][Decision] Management Port 9000 not exposed — RESOLVED: Exposed on host port 9002 (9002:9000) to avoid MinIO conflict while satisfying AC #2.

#### Patch
- [x] [Review][Patch] Missing `keycloak` database in `init.sql` [src/config/postgres/init.sql:1]
- [x] [Review][Patch] Documentation regression in `.env.example` [src/.env.example:19]
- [x] [Review][Patch] Contradiction regarding `openid` scope [src/config/realms/zachai-realm.json:56]
- [x] [Review][Patch] Inconsistent Keycloak health check timeouts [src/compose.yml:132]
- [x] [Review][Patch] Vague PostgreSQL image version [src/compose.yml:98]
- [x] [Review][Patch] Unquoted or brittle environment variables in healthchecks [src/compose.yml:109,126]
- [x] [Review][Patch] Missing error handling in PostgreSQL init script [src/config/postgres/init.sql:1]
- [x] [Review][Patch] Leftover Camunda placeholders in `init.sql` [src/config/postgres/init.sql:15]
- [x] [Review][Patch] Use `${POSTGRES_DB:-keycloak}` in healthcheck [src/compose.yml:109]

#### Defer
- [x] [Review][Defer] Overprivileged Database Access (Shared Superuser) [src/compose.yml:101] — deferred, pre-existing architectural choice
- [x] [Review][Defer] Missing container resource constraints (limits/reservations) [src/compose.yml:97] — deferred, pre-existing
