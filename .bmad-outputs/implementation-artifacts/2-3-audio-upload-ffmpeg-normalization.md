# Story 2.3: Audio Upload & FFmpeg Normalization

Status: done

<!-- Note: Validation is optional. Run validate-create-story (`bmad-create-story` → Validate Story) before dev-story. -->

## Story

As a Manager,
I can upload audio files (MP4, MP3, AAC, FLAC, WAV, etc.) to a project via presigned URL,
so that they are stored in MinIO and automatically normalized to 16 kHz mono PCM by the FFmpeg worker for transcription.

*(Epic wording: [Source: docs/epics-and-stories.md#Epic-2]. Admin users share the same upload privileges as Manager where noted in AC 1.)*

---

## Acceptance Criteria

1. **FastAPI Audio File Upload Endpoint:**
   - `POST /v1/projects/{project_id}/audio-files/upload` — Auth: **Manager or Admin** JWT. Body: `{filename: str, content_type: str}` where `content_type` is `audio/*` or `video/*`.
   - Returns HTTP 200 with `{object_key: str, presigned_url: str, expires_in: int}` (presigned PUT URL valid for **3600s**).
   - Returns HTTP **403** if role is Transcripteur or Expert (or missing Manager/Admin).
   - Returns HTTP 404 if project not found.
   - Returns HTTP **403** if project `status` is `completed` (completed projects are immutable for uploads).
   - Returns HTTP 400 if `content_type` is not audio/video.

2. **Audio File Status Tracking in PostgreSQL:**
   - `AudioFile` table exists from Story 2.2 with columns: `id (PK), project_id (FK→projects), filename, minio_path, normalized_path, duration_s, status (enum: uploaded|assigned|in_progress|transcribed|validated), uploaded_at, updated_at`.
   - **Add** nullable columns on `audio_files` (backward-compatible):
     - `validation_error`: `String(1024)` — last FFmpeg/validation error message
     - `validation_attempted_at`: `DateTime(timezone=True)` — timestamp of last normalization attempt
   - **Do not** add `status="error"` to `AudioFileStatus` — errors are tracked via `validation_error` / HTTP responses (Stripe/AWS-style separation of state vs error metadata).
   - Indexes: PK on `id`, FK on `project_id`, index on `(project_id, status)` for list queries.

3. **Browser Upload → MinIO (Direct, No FastAPI Proxy):**
   - FastAPI returns presigned PUT URL (via `presigned_client` + `MINIO_PRESIGNED_ENDPOINT`, Story 1.3).
   - Browser uploads directly to MinIO: `PUT {presigned_url}` with file body.
   - FastAPI does **not** receive audio binary data.

4. **Audio File Registration in Database:**
   - `POST /v1/projects/{project_id}/audio-files/register` — Auth: Manager or Admin. Body: `{object_key: str}`. Validates object exists in MinIO and key prefix `projects/{project_id}/audio/`.
   - Returns HTTP 201 with `AudioFile` payload (include `validation_error`, `validation_attempted_at` when present).
   - **Design:** Registration is an explicit API call (avoids upload/DB races).
   - **On successful registration** (`status=uploaded`): FastAPI **immediately** triggers normalization (calls shared `normalize_audio_file` logic from Task 3 — same request lifecycle; commit DB state appropriately so retries remain consistent).

5. **FFmpeg Normalization:**
   - **Trigger:** Automatic when a file is registered (Task 2 → Task 3). Optional **on-demand** endpoint for ops/testing (Task 4).
   - Worker URL: `{FFMPEG_WORKER_URL}/normalize` (internal Docker: `http://ffmpeg-worker:8765/normalize`).
   - Request body: `{input_bucket: "projects", input_key: "<minio path>", output_bucket: "projects", output_key: "<same base>.normalized.wav"}`.
   - Success response: `{status: "ok", output_key: "...", duration_s: float}`.
   - Set `AudioFile.status = in_progress` before calling worker; on success set `transcribed`, `normalized_path`, `duration_s`, clear `validation_error` if applicable; on failure keep `uploaded`, set `validation_error` + `validation_attempted_at`.
   - **5xx** from worker: operator may retry (log + return 500 to caller on sync path if applicable).
   - **4xx** from worker: store message in `validation_error`; do not auto-retry; map to HTTP 413/422 per Task 8.

6. **Error Handling:**
   - Missing project → HTTP 404 `{"error": "..."}`.
   - Invalid `content_type` → HTTP 400.
   - Project not `draft` or `active` (e.g. `completed`) when accepting uploads/register → HTTP **403** `{"error": "Project must be in draft or active status to accept audio files"}` (wording may vary; flat `{"error": "..."}` only).
   - FFmpeg worker unavailable → HTTP 500 `{"error": "FFmpeg service unavailable, retry later"}` (logged).
   - FFmpeg validation (4xx) → HTTP 422 with detail in `{"error": "..."}`.
   - All errors flat `{"error": "..."}` via existing handler (Story 2.1).

7. **Compose & Environment:**
   - FFmpeg worker service from Story 3.1; FastAPI reaches it on internal network.
   - **`FFMPEG_WORKER_URL`**: add to `REQUIRED_ENV_VARS` in `main.py` (**no default** — fail fast, same pattern as `CAMUNDA_REST_URL`). Document in `.env.example` and `compose.yml` for `fastapi`.

8. **Testing:**
   - **≥ 8 new tests** covering: upload (200), invalid content_type (400), missing project (404), role enforcement (403), **completed project forbidden (403)**, register (201), MinIO missing object (400), FFmpeg success/failure paths, status transitions.
   - Mock ffmpeg via `httpx` / patched client (Story 2.2 Camunda style). Mock DB with `AsyncMock` where existing fixtures apply.
   - **All 51** existing tests in `src/api/fastapi/test_main.py` must still pass after changes.

---

## Tasks / Subtasks

- [x] **Task 1** — Implement FastAPI audio upload request endpoint (AC: 1, 6)
  - [x] `POST /v1/projects/{project_id}/audio-files/upload`
  - [x] Role: Manager or Admin only (403 Transcripteur/Expert)
  - [x] Project exists (404)
  - [x] Project `status` in `{draft, active}` only (403 if `completed`)
  - [x] `content_type` audio/* or video/* (400)
  - [x] `object_key`: `projects/{project_id}/audio/{uuid}.{ext}` from `filename`
  - [x] `presigned_client.presigned_put_object(..., expires=3600)` (Story 1.3)
  - [x] Response 200: `object_key`, `presigned_url`, `expires_in`

- [x] **Task 2** — Implement audio file registration + auto-normalize (AC: 4, 5)
  - [x] `POST /v1/projects/{project_id}/audio-files/register`
  - [x] Role: Manager or Admin; project exists; project status draft/active (403 if completed)
  - [x] Validate `object_key` prefix; `internal_client.stat_object` (400 if missing)
  - [x] Insert `AudioFile` (`uploaded`); handle `IntegrityError` → 400
  - [x] After successful persist, invoke `normalize_audio_file` (Task 3) before returning 201 **or** ensure normalization runs in same logical flow with clear commit ordering (no orphaned `in_progress` if register rolls back)

- [x] **Task 3** — FFmpeg normalization logic (AC: 5, 6)
  - [x] `async def normalize_audio_file(db, audio_file: AudioFile, settings) -> ...` (signature as fits codebase)
  - [x] `status → in_progress` → POST normalize → on OK `transcribed` + paths + `duration_s`
  - [x] On 4xx: populate `validation_error`, `validation_attempted_at`; keep `uploaded`
  - [x] On 5xx: same error columns; allow retry; log project_id, audio_file_id, FFmpeg response body

- [x] **Task 4** — Optional on-demand normalize (AC: 5)
  - [x] `POST /v1/projects/{project_id}/audio-files/{audio_file_id}/normalize` — Manager/Admin; 404 if missing; 400 if status not `uploaded`; delegate Task 3; **202 Accepted** or 200 with updated entity (pick one and document; prefer 202 for long-ish work)

- [x] **Task 5** — ORM / schema (AC: 2)
  - [x] Add `validation_error`, `validation_attempted_at` on `AudioFile` in `src/api/fastapi/main.py`
  - [x] Add index `(project_id, status)` if not present
  - [x] Alembic/migrations: project rule was “nullable columns OK”; add migration if repo uses Alembic for Postgres (if no migration tool, document manual DDL in dev notes)

- [x] **Task 6** — FFmpeg integration config (AC: 5, 7)
  - [x] `FFMPEG_WORKER_URL` in `REQUIRED_ENV_VARS` (no default)
  - [x] Shared `httpx.AsyncClient` or factory; lifespan health check `GET {base}/health` — **warning** if down, non-blocking startup (match Story 2.2 non-blocking external deps pattern)

- [x] **Task 7** — Pydantic models (AC: 1, 4)
  - [x] `AudioUploadRequest`: `filename` — min_length=1, max_length=255, strip whitespace, forbid control chars and `\/:*?"<>|`, require extension; `content_type` regex whitelist e.g. `^audio/|^video/` with allowed subtypes per product needs
  - [x] `AudioUploadResponse`, `AudioRegisterRequest` (object_key path validation), `AudioFileResponse` (+ error fields), `AudioFileListResponse`

- [x] **Task 8** — Error handling (AC: 6)
  - [x] Map worker 413→413, 422→422, 5xx→500; MinIO errors as specified
  - [x] All `HTTPException(detail={"error": "..."})` consistent with custom handler

- [x] **Task 9** — Tests (AC: 8)
  - [x] Cover AC 8 bullets; mock MinIO + ffmpeg HTTP
  - [x] `pytest src/api/fastapi/test_main.py` — 51 + new tests green

- [x] **Task 10** — Compose / `.env.example` (AC: 7)
  - [x] `fastapi` environment: `FFMPEG_WORKER_URL=http://ffmpeg-worker:8765`
  - [x] `depends_on` health for ffmpeg-worker if not already

### Review Findings (2026-03-29 — bmad-code-review)

- [x] [Review][Patch] **Safe `duration_s` coercion** — Resolved: `_parse_duration_s()` logs and returns `None` on bad values; regression test `test_register_audio_success_invalid_duration_s`. [`main.py`]
- [x] [Review][Patch] **Existing DB vs `create_all`** — Resolved: lifespan comment documents brownfield limitation; reference DDL under Dev Notes below.
- [x] [Review][Defer] **Legacy presigned PUT** — `POST /v1/upload/request-put` remains Manager-only and uses string `project_id`; new project-scoped upload allows Admin and int `project_id`. Pre-existing surface from Story 1.3; unify or deprecate in a later story. [`main.py` ~714–727]

---

## Dev Notes

### Architecture compliance

- Presigned URLs after JWT + role check; binaries never through FastAPI ([Source: docs/architecture.md#5.-Sécurité]).
- FFmpeg Worker internal-only ([Source: docs/architecture.md#Internal-Shield]).
- `AudioFile` part of business model ([Source: docs/architecture.md#3.-Modèle-de-Données-Métier]).

### Project structure & files

- Primary implementation: `src/api/fastapi/main.py` (ORM, routes, env).
- Tests: `src/api/fastapi/test_main.py`.
- Compose / env: repository root `compose.yml` (or `docker-compose.yml`), `.env.example`.

### Brownfield PostgreSQL (Story 2.3 schema)

If `audio_files` already existed before Story 2.3, run equivalent DDL once (adjust schema name if needed):

```sql
ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS validation_error VARCHAR(1024);
ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS validation_attempted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_audio_files_project_status ON audio_files (project_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_files_project_minio_path ON audio_files (project_id, minio_path);
```

### References

- Epic 2 Story 2.3: [docs/epics-and-stories.md](docs/epics-and-stories.md)
- Story 2.2 patterns: `.bmad-outputs/implementation-artifacts/2-2-project-creation-label-studio-provisioning.md`
- Story 1.3 presigned: `.bmad-outputs/implementation-artifacts/1-3-presigned-url-engine-fastapi.md`
- FFmpeg worker contract: `.bmad-outputs/implementation-artifacts/3-1-ffmpeg-worker-normalization-batch.md`

---

## Developer Context: Code Patterns & Integration Points

### Presigned URL (Story 1.3)

- `internal_client` — FastAPI ↔ MinIO inside Docker (`MINIO_ENDPOINT`).
- `presigned_client` — URL hostname reachable by browser (`MINIO_PRESIGNED_ENDPOINT`).
- Existing reference: `POST /v1/upload/request-put` in `main.py` — reuse patterns; new routes are project-scoped under `/v1/projects/{project_id}/audio-files/...`.

### Error handling (Stories 2.1–2.2)

- Flat `{"error": "..."}` via exception handler; use `HTTPException(status_code=..., detail={"error": "..."})`.

### FFmpeg worker (Story 3.1)

- `POST /normalize` body and responses as in AC 5; `GET /health`.

### Testing fixture (Story 2.2)

- `mock_db` with `dependency_overrides[get_db]`; patch `decode_token`, MinIO clients, and ffmpeg HTTP client.

---

## Previous Story Intelligence (2.2)

- `Project` / `AudioFile` ORMs and Camunda integration live in `main.py`.
- Role checks use `get_roles(payload)` and set intersections with `Manager`/`Admin`.
- Async SQLAlchemy + `IntegrityError` rollback pattern established.

---

## Git Intelligence Summary

Recent commits: Story 2.3 story draft; Story 2.2 deferred patches applied; sprint status updates. Implementation for 2.3 not merged — gateway still exposes legacy `/v1/upload/request-put` (Manager-only) and project CRUD from 2.2.

---

## Test Coverage Checklist

- [x] Upload presigned URL happy path
- [x] Invalid content_type
- [x] Missing project
- [x] Wrong role (403)
- [x] Completed project (403)
- [x] Register success + auto-normalize success
- [x] Register + FFmpeg 4xx / 5xx
- [x] Register invalid key / MinIO absent
- [x] No regressions (51 baseline tests)

---

## Story Completion Status (BMad create-story)

**Regenerated:** 2026-03-29  
**Status:** done  

**Context engine:** Epic 2.3 text, architecture.md, live `main.py` (`AudioFile`, `ProjectStatus`, presigned pattern, `REQUIRED_ENV_VARS`), PATCH-GUIDE resolutions (roles aligned to Manager narrative + Admin in AC; validation columns; no `error` status enum; FFMPEG required; auto-normalize on register).  

**Dev agent record:** see below.

---

## Change Log

- **2026-03-29** — Story 2.3 implemented: project-scoped upload/register/normalize routes, `FFMPEG_WORKER_URL`, ORM columns + composite index + unique (project_id, minio_path), 13 new FastAPI tests (64 total).
- **2026-03-29** — Code review (batch patch): `_parse_duration_s`, lifespan `create_all` brownfield note, `test_register_audio_success_invalid_duration_s`; story marked **done**.

---

## Dev Agent Record

### Agent Model Used

Composer / GPT-5.1 (Cursor agent)

### Debug Log References

- `pytest src/api/fastapi/test_main.py` — 64 passed
- MinIO `S3Error` uses `(response, code, message, ...)` constructor in minio 7.x

### Completion Notes List

- On-demand normalize returns **200** with full `AudioFile` JSON (sync completion).
- `call_ffmpeg_normalize` maps worker **413/422** to same HTTP status after DB update; other worker errors → **500**. Connection errors → **500**.
- `AudioUploadRequest.content_type` validated in route for explicit **400** (not only Pydantic 422).
- `make_mock_project` in tests now uses real `ProjectStatus` enums so draft/active/completed guards behave correctly.
- **Post-review:** `_parse_duration_s()` for robust FFmpeg JSON; lifespan documents `create_all` vs migrations; brownfield DDL in Dev Notes; 65 tests.

### File List

- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `src/compose.yml`
- `src/.env.example`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `.bmad-outputs/implementation-artifacts/2-3-audio-upload-ffmpeg-normalization.md`

