# Story 5.2: secure-wss-handshake-ticket-redis

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created (2026-03-29 refresh). -->

## Story

**As a** user of the collaborative editor,  
**I want** to open a WebSocket connection using a short-lived, single-use ticket instead of putting my Keycloak JWT in the URL or query string,  
**so that** credentials are not leaked via browser history, proxies, or logs.

## Acceptance Criteria

1. **Ticket issuance (FastAPI)** — Given an authenticated user with role **Transcripteur**, **Expert**, or **Admin** (support; align with Golden Set / transcription routes), when they call `POST /v1/editor/ticket` with a valid body `{ document_id, permissions }`, then the API returns `{ ticket_id, ttl: 60 }` where `ticket_id` is an opaque string (e.g. UUID v4) and **no JWT or user secrets** appear in the response beyond what the client already holds. **MVP `document_id` contract:** use a **positive integer** equal to `AudioFile.id` (same entity as `audio_id` in §4). Story 5.1 (Hocuspocus) should use the same value as the Yjs document name / room id to avoid a second mapping layer.

2. **Redis contract** — The ticket is stored in **Redis** with **TTL 60 seconds**. The value MUST bind the ticket to **identity** (`sub` from JWT), **document_id**, and **permissions** so a future WSS peer (Hocuspocus) can authorize the connection. The ticket is **single-use**: after successful validation for a connection attempt, it MUST be consumed (invalid for reuse).

3. **Authorization before minting** — FastAPI MUST NOT mint a ticket unless the caller is allowed to access the target document:
   - **Transcripteur:** Load `AudioFile` by `id == document_id` with `selectinload(AudioFile.assignment)`. JWT `sub` MUST match `Assignment.transcripteur_id`; `AudioFile.status` MUST be in `{ assigned, in_progress }`. Mirror the gate in `post_golden_set_frontend_correction` (see `src/api/fastapi/main.py` ~L2067–L2100).
   - **Expert:** Role **Expert**; same `AudioFile` lookup; **no** assignment required; parent `Project.status` MUST be `ProjectStatus.ACTIVE` (`"active"` — enum in `src/api/fastapi/main.py` ~L186–L189). MVP: no per-expert project ACL (document in code comments / Dev Notes).
   - **Admin:** Bypass document ownership checks (same pattern as Admin on `frontend-correction` and `get_audio_transcription`).

4. **Compose & dependencies** — **Redis is currently commented out** — uncomment and wire it: volume `redis_data` (`src/compose.yml` ~L30), service block (~L164–L165), expose `REDIS_URL` to **fastapi** (e.g. `redis://redis:6379/0`), add `depends_on: redis: condition: service_healthy`, and fix the Layer 1 header comment (~L5). Match healthcheck pattern used by other services. Architecture: [Source: docs/architecture.md §1.A, diagram Redis node].

5. **Errors** — **401** if JWT missing/invalid; **403** if role or document access check fails; **404** if `document_id` does not map to a known audio/document; **503** if Redis unavailable (no silent fallback).

6. **Tests** — Automated tests cover: happy path mint; expired ticket; replay (second use fails); wrong user/document; wrong role.

7. **Docs** — Update `docs/api-mapping.md` §6: clarify **`document_id`** = integer `audio_id`; auth line to include **Admin** (parity with this story). Add a one-line **WSS flow** note: HTTPS `POST /v1/editor/ticket` → WSS handshake carries **only** the opaque `ticket_id` (query or subprotocol as chosen in 5.1), never JWT in the URL.

## Tasks / Subtasks

- [x] **Redis infrastructure** (AC: 2, 4)
  - [x] Uncomment/add `redis:7-alpine` (or pinned patch) + named volume `redis_data` + `healthcheck: redis-cli ping`
  - [x] Wire `REDIS_URL` into FastAPI service; add `depends_on: redis` with `condition: service_healthy`
  - [x] Add `redis>=5` (async `redis.asyncio`) to `src/api/fastapi/requirements.txt`; optional `hiredis` for performance

- [x] **Ticket mint endpoint** (AC: 1, 3, 5)
  - [x] Implement `POST /v1/editor/ticket` in `src/api/fastapi/main.py` (or small module e.g. `editor_ticket.py` imported from `main`)
  - [x] Reuse existing JWT/JWKS validation and `get_roles(payload)` / `realm_access.roles` (same style as `request_get` ~L1332–L1335 and `post_golden_set_frontend_correction`)
  - [x] Pydantic body: `document_id: int` (positive), `permissions: list[str]` or constrained enum — persist both in Redis JSON
  - [x] `SET` Redis key with `ex=60`; value = JSON `{"sub", "document_id", "permissions"}`; key `wss:ticket:{ticket_id}`

- [x] **Single-use semantics** (AC: 2)
  - [x] Document for Story 5.1 consumer: validation must **GETDEL** or use a short Lua script (SETNX consume) so concurrent duplicate connects are rejected

- [x] **Optional audit** (non-blocking)
  - [x] Architecture lists `WSSTicket` in PostgreSQL ([Source: docs/architecture.md §3]); either defer to a later story or insert an audit row on mint — do **not** duplicate Redis as second source of truth for validity

- [x] **Tests & docs** (AC: 6, 7)
  - [x] Extend `src/api/fastapi/test_main.py`: add `os.environ.setdefault("REDIS_URL", ...)` before import; mock or use **fakeredis** (async-compatible build) — add dev dependency if missing
  - [x] Update `docs/api-mapping.md` §6 (`document_id` type, Admin auth, WSS note)

## Dev Notes

### Implementation anchors (do not skip)

| Concern | Where |
|--------|--------|
| Required env vars | `REQUIRED_ENV_VARS` + `validate_env()` — append `REDIS_URL` when Redis becomes mandatory (`src/api/fastapi/main.py` ~L48–L67) |
| Shared HTTP/async clients | `lifespan()` — create `redis.asyncio.Redis.from_url()` after JWKS/DB init, `await redis.aclose()` in shutdown after yield (mirror `_ffmpeg_client` ~L443–L456) |
| Role extraction | `get_roles(payload)` (existing helper used across routes) |
| Test harness env | `test_main.py` sets env before `import main` (~L14–L27) — add `REDIS_URL`; patch Redis or inject fakeredis into app state if you refactor client access |
| Compose Redis stub | Commented template ~L164–165; volume ~L30 |

### Architecture compliance

- **Tickets WSS** — FastAPI generates one-time Redis ticket, TTL 60s; JWT never in WSS URL ([Source: docs/architecture.md §1.A, §5]).
- **Redis usage** — Also reserved for Hocuspocus pub/sub and LanguageTool cache ([Source: docs/prd.md stack table]); use **key namespaces** (`wss:ticket:`, `lt:cache:`, etc.) to avoid collisions.
- **TLS** — Local compose may use `ws:`; production target is **WSS / TLS 1.3** ([Source: docs/architecture.md §5]).

### Technical requirements

- **Stack:** Python 3.11, FastAPI, async Redis ([redis-py](https://github.com/redis/redis-py) 5.x async).
- **Env:** Add `REDIS_URL` to `REQUIRED_ENV_VARS` once the ticket endpoint ships; until then tests can set a dummy URL if import order requires it.
- **Key format:** Opaque `ticket_id`; server-side only mapping. Do not embed JWT or PII in the key.
- **TTL:** Exactly **60** seconds per PRD/architecture; return `ttl: 60` in JSON for client UX.
- **Permissions:** Accept `permissions` as a structured field (e.g. `read` / `write` strings); store in Redis payload for Hocuspocus to enforce later.

### File structure requirements

| Area | Path |
|------|------|
| Compose | `d:\zachai\src\compose.yml` |
| Gateway | `d:\zachai\src\api\fastapi\main.py` (+ optional `editor_ticket.py`) |
| Deps | `d:\zachai\src\api\fastapi\requirements.txt` |
| API contract | `d:\zachai\docs\api-mapping.md` |
| Tests | Under `src/api/fastapi/` or project test folder as existing stories use |

### Testing requirements

- Mirror patterns from Golden Set / assignment tests: async client, DB fixtures, mocked external services.
- Redis: use **fakeredis** for unit tests if already acceptable in repo; otherwise **testcontainers** with Redis image.

### Library / framework notes (latest tech)

- **redis-py 5.x:** Prefer `redis.asyncio.from_url()`; connection pooling at app lifespan; `GETDEL` for single-use consume where Redis ≥ 6.2 (default in `redis:7-alpine`).
- **Hocuspocus (Story 5.1):** Authentication typically reads a `token` or query parameter and validates server-side ([Tiptap Hocuspocus authentication](https://tiptap.dev/docs/hocuspocus/guides/authentication)) — this story supplies the **ticket** and Redis layout; 5.1 implements the WSS server consumer.

### Cross-story dependencies

- **Story 5.1** (Hocuspocus/Yjs) will consume tickets; avoid hard-coding a final WSS URL path until 5.1 defines the server — but **reserve** the handshake parameter name (`ticket` vs `token`) and document it in api-mapping.
- **Story 5.5 / PRD** — LanguageTool cache Redis: namespacing prevents clashes once implemented.

### Previous story intelligence

- **Epic 5 Story 5.1** is still **backlog**; there is no prior implementation story file in `implementation-artifacts` for 5-1. Reuse **FastAPI JWT + role** patterns from Stories 4.2 (transcripteur gate) and 2.4 (assignment).

### Git intelligence (recent commits)

- Recent commits: LoRA Camunda trigger, Golden Set, OpenVINO — no Redis or editor ticket code yet. Follow **existing** `main.py` style: env validation, `HTTPBearer`, structured `HTTPException` details, `lifespan` for external clients.

### Project context reference

- No `project-context.md` found in repo; rely on `docs/architecture.md`, `docs/prd.md`, `docs/api-mapping.md`, and `docs/epics-and-stories.md`.

## Dev Agent Record

### Agent Model Used

Cursor agent (Claude) — 2026-03-29 implementation; continuation pass completes docs/sprint/story metadata.

### Debug Log References

_(none)_

### Completion Notes List

- Redis `7.4-alpine` service + `redis_data` volume + FastAPI `REDIS_URL` / `depends_on` health in `src/compose.yml`.
- `editor_ticket.py`: `wss:ticket:{id}` JSON + `store_ticket` / `consume_wss_ticket` (**GETDEL**) for Story 5.1.
- `main.py`: `REDIS_URL` required; lifespan `redis.asyncio` connect + ping (degrades to 503 on mint if down); `POST /v1/editor/ticket` with Transcripteur / Expert / Admin gates aligned with Golden Set patterns.
- Tests: `fakeredis` + unreachable default `REDIS_URL`; coverage for happy path, replay, Expert inactive project, Redis 503, invalid permissions. Async `httpx.ASGITransport` + `await consume_wss_ticket` for same event loop as fakeredis (Python 3.14 / strict asyncio).
- `RequestValidationError` handler: `_validation_errors_json_safe` so `ctx.error` (e.g. ValueError) serializes to JSON on 422.
- `requirements.txt`: `redis>=5.0.0` (pure Python ; optional hiredis can be added later).
- `docs/api-mapping.md` §6 updated (document_id, Admin, WSS flow).
- **Optional audit:** `WSSTicket` PostgreSQL row **deferred** to a later story (no duplicate source of truth).

### File List

- `src/compose.yml`
- `src/api/fastapi/main.py`
- `src/api/fastapi/editor_ticket.py`
- `src/api/fastapi/requirements.txt`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`

### Change Log

- 2026-03-29 — Story 5.2: editor WSS ticket mint + Redis + tests + api-mapping §6; sprint status → review.
- 2026-03-30 — Code review patch: Transcripteur invalid audio status **409**; **401** tests for editor ticket; story + sprint → **done**.

### Review Findings

_(BMAD code review — 2026-03-30. Review layers synthesized in-session; parallel subagents were not invoked.)_

- [x] [Review][Patch] Transcripteur + wrong `AudioFile` status → **409** (aligned with `post_golden_set_frontend_correction`). [`src/api/fastapi/main.py` ~2276–2280] — fixed 2026-03-30 (+ `docs/api-mapping.md` §6)
- [x] [Review][Patch] AC6 asks for **401** when JWT missing/invalid; add an automated test on `POST /v1/editor/ticket` (no `Authorization` or invalid bearer) to lock the contract. [`src/api/fastapi/test_main.py`] — fixed 2026-03-30
- [x] [Review][Defer] `consume_wss_ticket` — `json.loads` can raise if Redis value is corrupted; Story 5.1 WSS peer should treat parse errors like missing ticket (fail closed). [`src/api/fastapi/editor_ticket.py` ~43–48] — deferred, consumer responsibility

---

## Traduction française (exigence document_output_language)

**Story :** En tant qu’utilisateur de l’éditeur collaboratif, je veux ouvrir une connexion WebSocket avec un ticket à courte durée et à usage unique (Redis, TTL 60s), afin que mon JWT Keycloak ne soit jamais exposé dans l’URL de connexion.

**Critères d’acceptation (résumé) :** Émission du ticket via FastAPI (`POST /v1/editor/ticket`), `document_id` = identifiant entier de l’audio, stockage Redis 60s, usage unique, contrôles d’accès (Transcripteur assigné, Expert + projet actif, Admin), Redis activé dans Docker Compose, erreurs explicites, tests automatisés, documentation alignée avec `api-mapping.md`.
