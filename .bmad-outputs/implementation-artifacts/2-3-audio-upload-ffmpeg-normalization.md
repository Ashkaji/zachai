# Story 2.3: Audio Upload & FFmpeg Normalization

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Transcripteur or Manager,
I can upload audio files (MP3, WAV, FLAC, etc.) to a project via presigned URL,
so that the audio is automatically normalized (16-bit PCM, mono, 16kHz) by the FFmpeg worker and made available for transcription.

---

## Acceptance Criteria

1. **FastAPI Audio File Upload Endpoint:**
   - `POST /v1/projects/{project_id}/audio-files/upload` — Auth: Manager or Admin JWT. Body: `{filename: str, content_type: str}` where content_type is `audio/*` or `video/*`. Returns HTTP 200 with `{object_key: str, presigned_url: str, expires_in: int}` (presigned PUT URL valid for 3600s). Returns HTTP 403 if role is Transcripteur or Expert. Returns HTTP 404 if project not found. Returns HTTP 400 if content_type not audio/video.

2. **Audio File Status Tracking in PostgreSQL:**
   - `AudioFile` table already created in Story 2.2 with columns: `id (PK), project_id (FK→projects), filename, minio_path, normalized_path, duration_s, status (enum: uploaded|assigned|in_progress|transcribed|validated), uploaded_at, updated_at`.
   - No schema changes needed (carried forward from Story 2.2).
   - Indexes: PK on id, FK on project_id, optional index on status for queries.

3. **Browser Upload → MinIO (Direct, No FastAPI Proxy):**
   - FastAPI returns presigned PUT URL (via `presigned_client` using `MINIO_PRESIGNED_ENDPOINT`, e.g., `localhost:9000`).
   - Browser uploads directly to MinIO: `PUT {presigned_url}` with audio file in body.
   - FastAPI does NOT receive audio binary data (security + performance pattern from Story 1.3).
   - Expected flow: Browser downloads presigned URL → Browser uploads → MinIO stores in `projects/{project_id}/audio/{uuid}.{ext}`.

4. **Audio File Registration in Database:**
   - After browser uploads to MinIO (managed externally by browser; FastAPI learns about it via webhook OR polling/scan OR explicit API call).
   - `POST /v1/projects/{project_id}/audio-files/register` — Auth: Manager or Admin. Body: `{object_key: str}` (path in MinIO, e.g., `projects/proj-1/audio/uuid.mp3`). Returns HTTP 201 with `{id, project_id, filename, minio_path, status: "uploaded", uploaded_at}`. Creates AudioFile record with status=UPLOADED.
   - Return 404 if project not found. Return 400 if object_key not found in MinIO or is outside `projects/{project_id}/audio/` prefix.
   - Design decision: registration is explicit API call (not automatic) to avoid race conditions between browser upload and DB write.

5. **FFmpeg Normalization Triggering:**
   - When AudioFile status is "uploaded", FastAPI can trigger normalization job via POST to FFmpeg worker: `http://ffmpeg-worker:8765/normalize`.
   - Request body: `{input_bucket: "projects", input_key: "projects/proj-1/audio/uuid.mp3", output_bucket: "projects", output_key: "projects/proj-1/audio/uuid.normalized.wav"}`.
   - FFmpeg worker returns: `{status: "ok", output_key: "...", duration_s: 125.5}` or error 413/422/500/504.
   - Update AudioFile.status = "in_progress" before calling FFmpeg, then status = "transcribed" + normalized_path + duration_s after success.
   - If FFmpeg fails (5xx): keep status = "uploaded", log error, return 500 to caller (operator should retry).
   - If FFmpeg validation fails (4xx): status = "error" (future), log error, do not retry (fix input).

6. **Error Handling:**
   - Missing project → HTTP 404 `{"error": "Project {project_id} not found"}`.
   - Invalid content_type → HTTP 400 `{"error": "content_type must be audio/* or video/*"}`.
   - Project status not draft/active → HTTP 400 `{"error": "Project must be in draft or active status to accept audio files"}`.
   - FFmpeg worker unavailable → HTTP 500 `{"error": "FFmpeg service unavailable, retry later"}` (log for ops).
   - FFmpeg validation error (4xx) → HTTP 422 `{"error": "FFmpeg validation failed: {detail}"}`.
   - All error responses follow `{"error": "..."}` flat format.

7. **Compose.yml & Environment:**
   - FFmpeg worker already deployed in Story 3.1 (no changes needed).
   - FastAPI can reach FFmpeg worker via internal Docker network: `http://ffmpeg-worker:8765`.
   - MinIO endpoint for browser uploads (MINIO_PRESIGNED_ENDPOINT) already configured in Story 1.3.

8. **Testing:**
   - At least 8 tests covering: audio upload request (201), invalid content_type (400), missing project (404), role enforcement (403), file registration (201), FFmpeg trigger success/failure, status transitions.
   - Mock FFmpeg worker HTTP calls at httpx level (similar to Camunda mocking in Story 2.2).
   - DB sessions mocked via AsyncMock.
   - All 51 tests from Stories 1.1–2.2 must still pass (no regressions).
   - Test file registration with non-existent MinIO path (400).

---

## Tasks / Subtasks

- [ ] **Task 1** — Implement FastAPI audio upload request endpoint (AC: 1)
  - [ ] Create `POST /v1/projects/{project_id}/audio-files/upload` endpoint
  - [ ] Role check: Manager or Admin only (403 if Transcripteur/Expert)
  - [ ] Validate project exists (404 if not)
  - [ ] Validate content_type is audio/* or video/* (400 if invalid)
  - [ ] Generate object_key: `projects/{project_id}/audio/{uuid}.{ext}`
  - [ ] Call presigned_client.presigned_put_object() (Story 1.3 pattern)
  - [ ] Return presigned URL + object_key + expires_in (3600s)
  - [ ] Status code 200 on success

- [ ] **Task 2** — Implement FastAPI audio file registration endpoint (AC: 4)
  - [ ] Create `POST /v1/projects/{project_id}/audio-files/register` endpoint
  - [ ] Role check: Manager or Admin only (403 if unauthorized)
  - [ ] Validate project exists (404 if not)
  - [ ] Parse body: object_key
  - [ ] Validate object_key is within `projects/{project_id}/audio/` prefix (400 if not)
  - [ ] Verify file exists in MinIO via stat_object() (400 if not)
  - [ ] Create AudioFile record: status="uploaded", minio_path=object_key, filename from object_key
  - [ ] Return 201 with AudioFile details
  - [ ] Handle IntegrityError gracefully (duplicate registration)

- [ ] **Task 3** — Implement FFmpeg normalization trigger logic (AC: 5)
  - [ ] Create async function: `async def normalize_audio_file(audio_file: AudioFile, ffmpeg_url: str) -> dict`
  - [ ] Update AudioFile.status = "in_progress" before calling FFmpeg
  - [ ] Call FFmpeg worker POST /normalize with correct request body
  - [ ] Parse response: extract output_key, duration_s
  - [ ] Update AudioFile.status = "transcribed", normalized_path, duration_s
  - [ ] Handle FFmpeg errors: 413 (too large), 422 (validation), 500/504 (service unavailable)
  - [ ] Log all errors with context (project_id, audio_file_id, FFmpeg response)
  - [ ] Return status dict or raise exception for caller to handle

- [ ] **Task 4** — Add endpoint to trigger normalization on-demand (AC: 5)
  - [ ] Create `POST /v1/projects/{project_id}/audio-files/{audio_file_id}/normalize` endpoint (optional, for testing/ops)
  - [ ] Role check: Manager or Admin only
  - [ ] Validate project and audio_file exist (404 if not)
  - [ ] Check audio_file.status = "uploaded" (400 if already in progress or completed)
  - [ ] Call normalize_audio_file() from Task 3
  - [ ] Return updated AudioFile with new status
  - [ ] Handle FFmpeg errors with proper HTTP codes

- [ ] **Task 5** — Update DatabaseSchema and ORM (AC: 2)
  - [ ] Verify AudioFile ORM model exists in src/api/fastapi/main.py (carried from Story 2.2)
  - [ ] Verify status enum: uploaded|assigned|in_progress|transcribed|validated (already defined)
  - [ ] Add index on (project_id, status) for efficient status queries
  - [ ] No schema migrations needed (table already exists)
  - [ ] Verify relationships: Project → [AudioFile] with cascade delete

- [ ] **Task 6** — Configure FFmpeg worker integration (AC: 5, 7)
  - [ ] Add FFmpeg worker URL to REQUIRED_ENV_VARS or with default: `FFMPEG_WORKER_URL=http://ffmpeg-worker:8765`
  - [ ] Create async HTTP client for FFmpeg worker (similar to Camunda client pattern from Story 2.2)
  - [ ] At startup (lifespan): test health check to FFmpeg worker (/health endpoint)
  - [ ] Log warning if FFmpeg worker unavailable (non-blocking)

- [ ] **Task 7** — Implement Pydantic request/response models (AC: 1, 4)
  - [ ] `AudioUploadRequest`: filename (str), content_type (str)
  - [ ] `AudioUploadResponse`: object_key (str), presigned_url (str), expires_in (int)
  - [ ] `AudioRegisterRequest`: object_key (str)
  - [ ] `AudioFileResponse`: id, project_id, filename, minio_path, normalized_path, duration_s, status, uploaded_at, updated_at
  - [ ] `AudioFileListResponse`: list of AudioFileResponse

- [ ] **Task 8** — Add error handling for audio operations (AC: 6)
  - [ ] Custom validation for content_type (audio/*, video/*)
  - [ ] Custom validation for object_key prefix (must be under `projects/{project_id}/audio/`)
  - [ ] MinIO stat_object() error handling (404 if file not found, other errors → 500)
  - [ ] FFmpeg worker error code mapping: 413→HTTP 413, 422→HTTP 422, 5xx→HTTP 500
  - [ ] Ensure all errors return flat `{"error": "..."}` format (via exception handler from Story 2.1)
  - [ ] Log all errors with context for ops debugging

- [ ] **Task 9** — Write unit + integration tests (AC: 8)
  - [ ] Test `POST /v1/projects/{id}/audio-files/upload` success (200) with valid project + role
  - [ ] Test invalid content_type (400)
  - [ ] Test missing project (404)
  - [ ] Test unauthorized role: Transcripteur/Expert (403)
  - [ ] Test `POST /v1/projects/{id}/audio-files/register` success (201)
  - [ ] Test register with non-existent object_key (400)
  - [ ] Test register with object_key outside expected prefix (400)
  - [ ] Test FFmpeg normalization trigger: success (status changes to "transcribed")
  - [ ] Test FFmpeg worker timeout/error (status remains "uploaded")
  - [ ] Mock FFmpeg worker HTTP calls (async httpx client)
  - [ ] Mock MinIO stat_object() calls
  - [ ] Verify all 51 previous tests still pass (no regressions)

- [ ] **Task 10** — Compose.yml and environment updates (AC: 7)
  - [ ] Verify ffmpeg-worker service exists and is healthy (already from Story 3.1)
  - [ ] Update fastapi service: add FFMPEG_WORKER_URL env var (default: `http://ffmpeg-worker:8765`)
  - [ ] Add FFmpeg worker to fastapi depends_on (condition: service_healthy) if not already present
  - [ ] Update `.env.example` with FFMPEG_WORKER_URL documentation
  - [ ] No new services needed (FFmpeg worker already running)

---

## Developer Context: Code Patterns & Integration Points

### Presigned URL Pattern (from Story 1.3)

The project uses TWO MinIO clients:
- **`internal_client`** (for FastAPI ↔ MinIO): points to `MINIO_ENDPOINT` (e.g., `minio:9000`)
- **`presigned_client`** (for browser ↔ MinIO): points to `MINIO_PRESIGNED_ENDPOINT` (e.g., `localhost:9000`)

Browser-side flow:
1. Browser: `POST /v1/upload/request-put` → FastAPI
2. FastAPI: `presigned_client.presigned_put_object(...)` → returns signed URL
3. Browser: `PUT {signed_url}` → uploads directly to MinIO (FastAPI NOT involved)
4. Browser: tells FastAPI (via callback API) that upload is complete

For this story, the callback is: `POST /v1/projects/{id}/audio-files/register` with the object_key.

### Error Handling Pattern (from Stories 2.1 & 2.2)

All FastAPI endpoints follow a consistent pattern:
```python
@app.post("/v1/path")
async def endpoint(...):
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "..."})

    result = await db.execute(select(Model).where(...))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail={"error": "..."})

    try:
        # do work
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail={"error": "..."})

    return {"field": obj.field, ...}
```

Custom exception handler returns flat `{"error": "..."}` format (already configured in main.py from Story 2.1).

### FFmpeg Worker Integration (from Story 3.1)

The FFmpeg worker is a separate FastAPI service running on `ffmpeg-worker:8765`.

**POST /normalize** endpoint:
- **Request**: `{"input_bucket": "projects", "input_key": "projects/proj-1/audio/file.mp3", "output_bucket": "projects", "output_key": "projects/proj-1/audio/file.normalized.wav"}`
- **Response (200)**: `{"status": "ok", "output_key": "...", "duration_s": 125.5}`
- **Response (413)**: `{"error": "File too large: X bytes"}` — exceeded MAX_FILE_SIZE
- **Response (422)**: `{"error": "FFmpeg command failed: ..."}` — invalid audio format or FFmpeg error
- **Response (500)**: `{"error": "MinIO download failed: ..."}` or `{"error": "MinIO upload failed: ..."}` — I/O issues
- **Response (504)**: `{"error": "FFmpeg timeout"}` — took too long

**GET /health**: Returns `{"status": "ok"}` if worker is healthy.

### Testing Pattern (from Stories 2.1 & 2.2)

Test fixture:
```python
@pytest.fixture
def mock_db():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.begin_nested = MagicMock(return_value=_FakeNestedTransaction())
    async def override():
        yield mock_session
    main.app.dependency_overrides[main.get_db] = override
    yield mock_session
    main.app.dependency_overrides.pop(main.get_db, None)
```

Mocking external services:
```python
with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
     patch.object(main.presigned_client, "presigned_put_object", return_value="http://..."), \
     patch.object(main, "ffmpeg_client") as mock_ffmpeg:
    mock_ffmpeg.post.return_value = AsyncMock(status_code=200, json=lambda: {"status": "ok", "duration_s": 125})
    response = client.post(...)
    assert response.status_code == 200
```

---

## Previous Story Intelligence

**Story 2.2 Deliverables Used:**
- `AudioFile` ORM model (ready to use, no changes)
- `Project` ↔ `AudioFile` relationship with cascade delete
- Error handling pattern with flat `{"error": "..."}` format
- Role-based access control pattern (Manager/Admin only)
- HTTPException usage for all error cases

**Story 3.1 Deliverables Used:**
- FFmpeg worker running on `ffmpeg-worker:8765` with `/normalize` and `/health` endpoints
- MinIO integration pattern for file I/O (get_object, put_object, stat_object)
- Subprocess management and error handling

**Story 1.3 Deliverables Used:**
- Presigned URL generation via MinIO `presigned_put_object()`
- Two-client pattern: `internal_client` + `presigned_client`
- Browser-side upload flow (no FastAPI binary proxy)

---

## Git Intelligence Summary

Recent commits show:
1. Story 2.2 patterns: Async/await, httpx client for Camunda, role checks, transaction management
2. Story 3.1 patterns: Subprocess spawning, MinIO get/put, error handling for external services
3. Story 2.1 patterns: SQLAlchemy async ORM, Pydantic models, HTTPException custom handler, testing mocks

Recommendation: Follow exact same patterns from Stories 2.1 & 2.2 for consistency. Use `httpx.AsyncClient` for FFmpeg worker calls (matching Camunda pattern).

---

## Test Coverage Checklist

- [ ] Upload request (presigned URL generation)
- [ ] Invalid content_type validation
- [ ] Missing project (404)
- [ ] Unauthorized role (403)
- [ ] File registration success
- [ ] File not found in MinIO (400)
- [ ] Invalid object_key prefix (400)
- [ ] FFmpeg normalization success (status → "transcribed", duration populated)
- [ ] FFmpeg error handling (413, 422, 500, 504)
- [ ] FFmpeg worker unavailable (500 with logged error)
- [ ] All 51 pre-existing tests still pass

---

## Story Completion Status

**Created:** 2026-03-29
**Status:** ready-for-dev
**Context Engine Analysis:** Complete developer guide with acceptance criteria, implementation tasks, code patterns, integration points, and comprehensive test strategy.

**Quality Checklist:**
- ✅ Dependencies mapped (2.2, 3.1, 1.3)
- ✅ Code patterns extracted and documented
- ✅ FFmpeg worker API contract defined
- ✅ Error handling strategy aligned with project standards
- ✅ Testing approach clarified with examples
- ✅ 10 implementation tasks specified
- ✅ 11+ test cases outlined
- ✅ Environment and compose.yml requirements noted

**Developer is ready to implement with zero ambiguity.**
