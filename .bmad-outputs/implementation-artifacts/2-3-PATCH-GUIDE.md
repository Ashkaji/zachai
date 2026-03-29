# Story 2.3 Patch Guide: Research-Backed Solutions

**Date:** 2026-03-29
**Purpose:** Fix 3 critical + 3 high-priority issues in Story 2.3 using industry best practices
**Research:** AWS S3, OWASP, Stripe, GitHub, Pydantic documentation

---

## CRITICAL PATCHES (Must Apply Before Dev)

### PATCH 1: Fix Role Authorization Conflict

**Issue:** User story says "Transcripteur or Manager" but AC 1 says "Manager/Admin only"

**Research Finding:** AWS presigned URLs use the **authorization of the user who generates the URL**. The pattern is: authorize who generates URL (Manager), not who can use it (anyone with URL can upload).

**Recommended Solution:** Manager/Admin generate presigned URLs; Transcripteur can be given URLs to use.

**How to Fix Story 2.3:**

**Option 1 (Current spec):** Keep "Manager/Admin only" — most secure, clearest audit trail
```markdown
# Line 9: Change user story
As a Manager,
I can upload audio files ...

# Line 18 in AC 1: Keep as-is
Returns HTTP 403 if role is Transcripteur or Expert.
```

**Option 2 (Recommended):** Allow Transcripteur to generate URLs too — better UX, still auditable
```markdown
# Line 9: Change user story
As a Transcripteur or Manager,
I can upload audio files ...

# Line 18 in AC 1: Change role check
Role check: Manager, Admin, or Transcripteur (403 if Expert).
Log user ID and role for audit trail.
```

**DECISION REQUIRED:** Choose Option 1 or 2. Recommendation: **Option 1** (keep current spec) for maximum security; upgrade to Option 2 in next sprint if UX issues arise.

---

### PATCH 2: Fix Missing Error Status Handling

**Issue:** Spec mentions `status="error"` but `AudioFileStatus` enum doesn't have it.

**Research Finding:** Industry best practice (Stripe, AWS) separates **status** (state machine progression) from **errors** (metadata). Use separate `validation_error` field instead.

**How to Fix Story 2.3:**

**Step 1:** Update AC 2 (Lines 20-23) to add error tracking columns:

```markdown
2. **Audio File Status Tracking in PostgreSQL:**
   - `AudioFile` table already created in Story 2.2 with columns: `id (PK), project_id (FK→projects), filename, minio_path, normalized_path, duration_s, status (enum: uploaded|assigned|in_progress|transcribed|validated), uploaded_at, updated_at`.
   + NEW COLUMNS for error tracking:
   + `validation_error: str | None` — stores FFmpeg validation error message (1024 chars max)
   + `validation_attempted_at: datetime | None` — timestamp of last validation attempt
   - No schema migrations needed (adding nullable columns is safe).
   - Indexes: PK on id, FK on project_id, optional index on status for queries.
```

**Step 2:** Update AC 5 (Lines 37-43) to clarify status handling:

```markdown
5. **FFmpeg Normalization Triggering:**
   - When AudioFile status is "uploaded", FastAPI can trigger normalization job via POST to FFmpeg worker: `http://ffmpeg-worker:8765/normalize`.
   - Request body: `{input_bucket: "projects", input_key: "projects/proj-1/audio/uuid.mp3", output_bucket: "projects", output_key: "projects/proj-1/audio/uuid.normalized.wav"}`.
   - FFmpeg worker returns: `{status: "ok", output_key: "...", duration_s: 125.5}` or error 413/422/500/504.
   - Update AudioFile.status = "in_progress" before calling FFmpeg, then status = "transcribed" + normalized_path + duration_s after success.
   - If FFmpeg fails (5xx): keep status = "uploaded", store error in validation_error column, log error, return 500 to caller (operator should retry).
   - If FFmpeg validation fails (4xx): keep status = "uploaded", store error reason in validation_error column + validation_attempted_at timestamp, do not retry (user must fix input or delete file).
```

**Step 3:** Update Task 5 (Lines 109-114) to include new columns:

```markdown
- [ ] **Task 5** — Update DatabaseSchema and ORM (AC: 2)
  - [ ] Verify AudioFile ORM model exists in src/api/fastapi/main.py (carried from Story 2.2)
  - [ ] Verify status enum: uploaded|assigned|in_progress|transcribed|validated (already defined)
  + [ ] Add validation_error column: String(1024), nullable
  + [ ] Add validation_attempted_at column: DateTime(timezone=True), nullable
  - [ ] Add index on (project_id, status) for efficient status queries
  - [ ] No schema migrations needed (adding nullable columns is backward-compatible)
  - [ ] Verify relationships: Project → [AudioFile] with cascade delete
```

---

### PATCH 3: Add Project Status Validation to Task 1

**Issue:** AC 6 requires project status check, but Task 1 doesn't implement it.

**Research Finding:** Completed projects should be read-only (immutability for audit trail).

**How to Fix Story 2.3:**

**Update Task 1 (Lines 69-77):**

```markdown
- [ ] **Task 1** — Implement FastAPI audio upload request endpoint (AC: 1)
  - [ ] Create `POST /v1/projects/{project_id}/audio-files/upload` endpoint
  - [ ] Role check: Manager or Admin only (403 if Transcripteur/Expert)
  - [ ] Validate project exists (404 if not)
  + [ ] Validate project.status is "active" or "draft", not "completed" (403 if completed)
  - [ ] Validate content_type is audio/* or video/* (400 if invalid)
  - [ ] Generate object_key: `projects/{project_id}/audio/{uuid}.{ext}`
  - [ ] Call presigned_client.presigned_put_object() (Story 1.3 pattern)
  - [ ] Return presigned URL + object_key + expires_in (3600s)
  - [ ] Status code 200 on success
```

---

## HIGH-PRIORITY PATCHES (Strongly Recommended)

### PATCH 4: Specify Pydantic Validation Rules

**Issue:** Task 7 lists models but validation rules are missing.

**Research Finding:** OWASP recommends whitelist of allowed characters, length limits, no control chars.

**How to Fix Story 2.3:**

**Update Task 7 (Lines 122-127) with validation rules:**

```markdown
- [ ] **Task 7** — Implement Pydantic request/response models (AC: 1, 4)
  - [ ] `AudioUploadRequest`:
        * filename: str, min_length=1, max_length=255, no forbidden chars (/ \ : * ? " < > |), no control chars, no leading/trailing space, must have extension
        * content_type: str, pattern=^audio/(mpeg|wav|mp4|aac|ogg|flac|x-wav|x-flac)$
  - [ ] `AudioUploadResponse`: object_key (str), presigned_url (str), expires_in (int)
  - [ ] `AudioRegisterRequest`: object_key (str), must be within projects/{project_id}/audio/ prefix
  - [ ] `AudioFileResponse`: id, project_id, filename, minio_path, normalized_path, duration_s, status, validation_error, validation_attempted_at, uploaded_at, updated_at
  - [ ] `AudioFileListResponse`: list of AudioFileResponse
```

**Add to Task 8 (error handling):**
```markdown
- [ ] **Task 8** — Add error handling for audio operations (AC: 6)
  - [ ] Filename validation: reject forbidden chars (/ \ : * ? " < > |), control chars, reserved names
  - [ ] Content-type validation: must match pattern audio/(mpeg|wav|mp4|aac|ogg|flac|...)
  - [ ] Custom validation for object_key prefix (must be under `projects/{project_id}/audio/`)
  - [ ] MinIO stat_object() error handling (404 if file not found, other errors → 500)
  - [ ] FFmpeg worker error code mapping: 413→HTTP 413, 422→HTTP 422, 5xx→HTTP 500
  - [ ] Ensure all errors return flat `{"error": "..."}` format (via exception handler from Story 2.1)
  - [ ] Log all errors with context for ops debugging
```

---

### PATCH 5: Clarify FFMPEG_WORKER_URL Environment Variable

**Issue:** Task 6 wording is ambiguous — "REQUIRED_ENV_VARS or with default"

**Research Finding:** Should be REQUIRED, following Story 2.2 pattern (CAMUNDA_REST_URL is required).

**How to Fix Story 2.3:**

**Update Task 6 (Lines 116-120):**

```markdown
- [ ] **Task 6** — Configure FFmpeg worker integration (AC: 5, 7)
  - [ ] Add FFMPEG_WORKER_URL to REQUIRED_ENV_VARS: `FFMPEG_WORKER_URL=http://ffmpeg-worker:8765`
  - [ ] (No default value — fail fast if not configured, matching CAMUNDA_REST_URL pattern)
  - [ ] Create async HTTP client for FFmpeg worker (similar to Camunda client pattern from Story 2.2)
  - [ ] At startup (lifespan): test health check to FFmpeg worker (/health endpoint)
  - [ ] Log warning if FFmpeg worker unavailable (non-blocking, log and continue)
```

**Add to Task 10 (environment):**
```markdown
- [ ] Update `.env.example` with:
      FFMPEG_WORKER_URL=http://ffmpeg-worker:8765
      Note: Must match the internal Docker network hostname of FFmpeg worker
```

---

### PATCH 6: Clarify Normalization Trigger Pattern

**Issue:** Story doesn't specify WHEN/HOW FFmpeg normalization happens.

**Research Finding:** Automatic background job is simplest pattern for on-premise system.

**How to Fix Story 2.3:**

**Update AC 5 (Lines 37-43) to clarify trigger pattern:**

```markdown
5. **FFmpeg Normalization Triggering:**
   + **Design Decision: Automatic triggering on file registration**
   + When AudioFile is registered (status="uploaded"), FastAPI immediately enqueues an FFmpeg normalization job.
   + Job is processed by a background worker (Camunda External Task or similar async pattern).
   - Normalization job calls FFmpeg worker: `http://ffmpeg-worker:8765/normalize`
   - Request body: `{input_bucket: "projects", input_key: "projects/proj-1/audio/uuid.mp3", output_bucket: "projects", output_key: "projects/proj-1/audio/uuid.normalized.wav"}`.
   - FFmpeg worker returns: `{status: "ok", output_key: "...", duration_s: 125.5}` or error 413/422/500/504.
   - On success: update AudioFile.status = "transcribed", normalized_path, duration_s
   - On failure: keep status = "uploaded", store error in validation_error column
   + Optional: On-demand normalization endpoint (POST /v1/projects/{id}/audio/{file_id}/normalize) for testing/ops (Task 4)
   + Note: Automatic triggering allows the system to process files at its own pace. Operators can monitor progress via GET /v1/projects/{id}/audio-files to see status of all files.
```

**Add to Task 3 (Lines 90-98):**
```markdown
- [ ] **Task 3** — Implement FFmpeg normalization trigger logic (AC: 5)
  - [ ] Create async function: `async def normalize_audio_file(audio_file: AudioFile, ffmpeg_url: str) -> dict`
  - [ ] This function will be called automatically when file is registered (Task 2)
  - [ ] Update AudioFile.status = "in_progress" before calling FFmpeg
  - [ ] Call FFmpeg worker POST /normalize with correct request body
  - [ ] Parse response: extract output_key, duration_s
  - [ ] Update AudioFile.status = "transcribed", normalized_path, duration_s
  - [ ] Handle FFmpeg errors: 413 (too large), 422 (validation), 500/504 (service unavailable)
  - [ ] Log all errors with context (project_id, audio_file_id, FFmpeg response)
  - [ ] On error: keep status="uploaded", store error in validation_error column
  - [ ] Return status dict for logging
```

**Clarify in Task 4:**
```markdown
- [ ] **Task 4** — Add endpoint to trigger normalization on-demand (AC: 5) (OPTIONAL, for testing/ops)
  - [ ] Create `POST /v1/projects/{project_id}/audio-files/{audio_file_id}/normalize` endpoint
  - [ ] Role check: Manager or Admin only
  - [ ] Validate project and audio_file exist (404 if not)
  - [ ] Check audio_file.status = "uploaded" (400 if already in progress or completed)
  - [ ] Call normalize_audio_file() from Task 3 to trigger normalization
  - [ ] Return 202 Accepted with audio_file details
  - [ ] Note: This endpoint is optional and primarily for testing/debugging
```

---

## SUMMARY OF PATCHES

| Patch # | Issue | Type | Changes |
|---------|-------|------|---------|
| 1 | Role authorization | Critical | Update user story OR update AC 1 role check (choose one) |
| 2 | Missing error status | Critical | Add 2 columns to schema, update AC 2, AC 5, Task 5 |
| 3 | Missing project status validation | Critical | Add validation to Task 1 subtasks |
| 4 | Missing Pydantic validation rules | High | Add validation rules to Task 7 and Task 8 |
| 5 | Unclear FFMPEG_WORKER_URL | High | Clarify as REQUIRED in Task 6 + Task 10 |
| 6 | Unclear normalization trigger | High | Update AC 5 + Task 3 + Task 4 to clarify auto-trigger |

---

## Application Instructions

### Step 1: Resolve Patch 1 (Role Authorization)

**Decision:** Which option?
- **Option 1:** Keep "Manager/Admin only" (most secure, current spec)
- **Option 2:** Allow "Transcripteur, Manager, Admin" (better UX)

**Recommendation:** Option 1 (stay with current spec). If UX problems arise, upgrade in next sprint.

### Step 2: Apply Patches 2-6

1. Open `.bmad-outputs/implementation-artifacts/2-3-audio-upload-ffmpeg-normalization.md`
2. Apply each patch in order (top to bottom)
3. Each patch shows old text and new text — replace old with new
4. Verify story is internally consistent after each patch

### Step 3: Validation

After applying patches:
- [ ] No contradictions between user story, AC, and tasks
- [ ] All tasks have clear, testable subtasks
- [ ] Pydantic models have validation rules specified
- [ ] Error handling is explicit for all error cases
- [ ] Database schema changes are documented
- [ ] Normalization trigger pattern is clear (automatic on registration)

### Step 4: Ready for Dev

Once patches applied:
1. Change story status: `ready-for-dev` (already is)
2. Assign developer via `/bmad-dev-story 2.3`
3. Developer can proceed with high confidence (no ambiguities)

---

## Patch Difficulty Assessment

- **Patch 1:** 5 min (one-line user story change or one AC change)
- **Patch 2:** 10 min (add 2 columns + clarify 2 ACs + 1 task)
- **Patch 3:** 5 min (add 1 subtask to Task 1)
- **Patch 4:** 15 min (add validation rules to Task 7 + 8)
- **Patch 5:** 5 min (clarify FFMPEG_WORKER_URL wording)
- **Patch 6:** 10 min (clarify normalization trigger pattern across AC 5, Task 3, Task 4)

**Total effort: ~50 minutes**

---

## Research Sources

This patch guide is based on:
- AWS S3 Presigned URL Security Guide
- OWASP File Upload Cheat Sheet (2024)
- Stripe API Error Handling Documentation
- Pydantic v2 Validation Best Practices
- GitHub / GitLab Authorization Patterns

All recommendations align with industry standards and ZachAI's architecture (async/await, Camunda patterns, MinIO integration).
