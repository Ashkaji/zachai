# Story 2.3: Audio Upload & FFmpeg Normalization — Codebase Patterns

**Date:** 2026-03-29
**Context:** Extracted from ZachAI codebase (Stories 1.3, 2.1, 2.2) to inform Story 2.3 design and implementation.

---

## 1. Audio File ORM Model

**Location:** `src/api/fastapi/main.py:192–210`

```python
class AudioFile(Base):
    __tablename__ = "audio_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    minio_path: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[AudioFileStatus] = mapped_column(
        SAEnum(AudioFileStatus), default=AudioFileStatus.UPLOADED, nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

**Key Design Points:**
- `project_id` → CASCADE delete (if project deleted, all audio files deleted)
- `minio_path` stores uploaded original file location (e.g., `projects/proj-1/audio/file.mp3`)
- `normalized_path` stores normalized WAV output (populated after FFmpeg processing)
- `duration_s` calculated by FFmpeg worker post-normalization
- `status` enum tracks file state: `UPLOADED → ASSIGNED → IN_PROGRESS → TRANSCRIBED → VALIDATED`
- `uploaded_at` and `updated_at` auto-populated with server timestamps

---

## 2. FFmpeg Worker API: POST /normalize

**Location:** `src/workers/ffmpeg-worker/main.py:59–137`

### Request Model

```python
class NormalizeRequest(BaseModel):
    input_bucket: str      # Source bucket in MinIO (e.g., "projects")
    input_key: str         # Object key (e.g., "proj-1/audio/original.mp3")
    output_bucket: str     # Destination bucket (e.g., "projects")
    output_key: str        # Output key (e.g., "proj-1/audio/normalized.wav")
```

### Response (Success)

```python
{
    "status": "ok",
    "output_key": "proj-1/audio/normalized.wav",
    "duration_s": 125.5
}
```

### Error Responses

| Status | Error Case |
|--------|-----------|
| 413 | File too large (>1GB) |
| 404 | Input file not found on disk after download |
| 422 | FFmpeg processing failed (malformed audio) / No output file produced |
| 504 | FFmpeg timeout (>600s) |
| 500 | MinIO stat/download/upload failure, subprocess error, job directory creation |

### Processing Pipeline

1. **Validate & Download:** Check file size via MinIO stat, download to `/tmp/ffmpeg-worker/{job_id}/`
2. **Normalize:** Run FFmpeg with fixed output spec:
   - Codec: `pcm_s16le` (PCM 16-bit signed little-endian)
   - Channels: Mono (1 channel)
   - Sample rate: 16kHz
   - Output format: WAV
3. **Duration Extraction:** Call `_get_wav_duration()` helper (implementation below)
4. **Upload:** Push normalized WAV to MinIO output bucket
5. **Cleanup:** Delete job directory (even on failure)

**FFmpeg Command:**
```bash
ffmpeg \
  -i /tmp/ffmpeg-worker/{job_id}/input{ext} \
  -acodec pcm_s16le \
  -ac 1 \
  -ar 16000 \
  -y \
  /tmp/ffmpeg-worker/{job_id}/output.wav
```

---

## 3. Presigned URL Pattern

**Location:** `src/api/fastapi/main.py:522–554` (POST /v1/upload/request-put)

### Request Model

```python
class PutRequestBody(BaseModel):
    project_id: str       # Project identifier
    filename: str         # Original filename (e.g., "interview_2026.mp3")
    content_type: str     # MIME type (e.g., "audio/mpeg")
```

### Response

```python
{
    "presigned_url": "http://localhost:9000/projects/proj-1/audio/interview_2026.mp3?X-Amz-Signature=xyz&...",
    "object_key": "projects/proj-1/audio/interview_2026.mp3",
    "expires_in": 3600
}
```

### Key Design Details

**Object Path Construction:**
- Internal (no bucket): `{project_id}/audio/{filename}`
- External (full key): `projects/{project_id}/audio/{filename}`

**MinIO Client Setup:**
```python
# Two clients with different endpoints:
# 1. Internal client (minio:9000) — for admin ops
internal_client = Minio(endpoint="minio:9000", ...)

# 2. Presigned client (localhost:9000) — generates browser-accessible URLs
presigned_client = Minio(endpoint="localhost:9000", ...)
presigned_client._region_map = {bucket: "us-east-1" for bucket in _MINIO_BUCKETS}
```

**Security Constraints:**
- Manager role required
- URL expires in 1 hour
- Direct browser→MinIO upload (FastAPI never touches binary data)

**Presigned URL Generation:**
```python
presigned_url = presigned_client.presigned_put_object(
    bucket_name="projects",
    object_name=f"{project_id}/audio/{filename}",
    expires=timedelta(hours=1),
)
```

---

## 4. Project ↔ AudioFile Relationship

**Location:** `src/api/fastapi/main.py:157–189`

### Project Model (ORM Relations)

```python
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = ...
    name: Mapped[str] = ...
    nature_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("natures.id", ondelete="RESTRICT"), nullable=False
    )
    # ... other fields ...
    created_at: Mapped[datetime] = ...
    updated_at: Mapped[datetime] = ...

    # Relationships
    nature: Mapped["Nature"] = relationship("Nature", lazy="selectin")
    audio_files: Mapped[list["AudioFile"]] = relationship(
        "AudioFile", cascade="all, delete-orphan", lazy="selectin"
    )
```

### Relationship Design

- **One-to-Many:** `Project` → multiple `AudioFile` records
- **Cascade Delete:** If project deleted, all its audio files deleted
- **Lazy Loading:** `lazy="selectin"` — eagerly load audio_files when fetching Project
- **Foreign Key:** `AudioFile.project_id` → `Project.id` with `ondelete="CASCADE"`

### API Contract

```python
@app.get("/v1/projects/{project_id}")
async def get_project(project_id: int, ...) -> dict:
    # Returns:
    {
        "id": 1,
        "name": "Project A",
        "nature_name": "Camp Biblique",
        "status": "draft",
        "manager_id": "user-123",
        "created_at": "2026-03-28T10:00:00Z",
        "audio_files": [
            {
                "id": 1,
                "filename": "interview.mp3",
                "minio_path": "projects/1/audio/interview.mp3",
                "normalized_path": "projects/1/audio/normalized.wav",
                "duration_s": 125.5,
                "status": "uploaded",
                "uploaded_at": "2026-03-28T10:05:00Z"
            }
        ]
    }
```

---

## 5. Error Handling Patterns

### Exception Handler Setup

**Location:** `src/api/fastapi/main.py:308–334`

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return flat {"error": "..."} body instead of FastAPI default {"detail": ...}."""
    detail = exc.detail
    if isinstance(detail, dict):
        body = detail
    else:
        body = {"error": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors. Return 400 for production_goal mismatches per spec AC 6."""
    errors = exc.errors()
    # Check if error is about production_goal field
    for error in errors:
        if error.get("loc") and "production_goal" in error.get("loc", ()):
            return JSONResponse(
                status_code=400,
                content={"error": "production_goal must be one of: livre, sous-titres, dataset, archive"},
            )
    # For other validation errors, return 422 (Pydantic default)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )
```

### Common HTTP Exception Patterns in CRUD

**Role Authorization:**
```python
roles = get_roles(payload)
if "Manager" not in roles:
    raise HTTPException(status_code=403, detail={"error": "Manager role required"})
```

**Resource Not Found:**
```python
result = await db.execute(select(Nature).where(Nature.id == nature_id))
nature = result.scalar_one_or_none()
if not nature:
    raise HTTPException(status_code=404, detail={"error": "Nature not found"})
```

**Integrity Violation (Duplicate):**
```python
try:
    async with db.begin_nested():
        db.add(nature)
        await db.flush()
        # ... add related records ...
    await db.commit()
except IntegrityError:
    await db.rollback()
    raise HTTPException(status_code=400, detail={"error": "Nature name already exists"})
```

**Invalid Input (Enum/Pattern):**
```python
new_status = body.status
valid_values = {s.value for s in ProjectStatus}
if new_status not in valid_values:
    raise HTTPException(
        status_code=400,
        detail={"error": f"Invalid status: {new_status}"},
    )
```

**External Service Failure (Non-Blocking):**
```python
try:
    resp = await camunda_client.post(
        "/process-definition/key/project-lifecycle/start",
        json={"variables": variables, "withVariablesInReturn": True},
    )
    if 200 <= resp.status_code < 300:
        # Success
        process_id = resp.json().get("id")
    else:
        logger.error("Camunda start failed: %s — project created but workflow not triggered", resp.status_code)
except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as exc:
    logger.error("Camunda unavailable (network error): %s — project created but workflow not triggered", exc)
```

**MinIO Error Handling:**
```python
try:
    presigned_url = presigned_client.presigned_put_object(
        bucket_name="projects",
        object_name=object_name,
        expires=timedelta(hours=1),
    )
except Exception as exc:
    logger.error("MinIO presigned_put_object failed: %s", exc)
    raise HTTPException(status_code=500, detail={"error": "Failed to generate upload URL"})
```

---

## 6. Testing Patterns

**Location:** `src/api/fastapi/test_main.py`

### Mock AsyncSession Pattern

```python
@pytest.fixture
def mock_db():
    """Override get_db dependency with an AsyncMock session; clean up after each test."""
    mock_session = AsyncMock()
    # Sync methods on AsyncSession — must be plain MagicMock, not AsyncMock
    mock_session.add = MagicMock()
    mock_session.expire = MagicMock()
    # begin_nested() must return an async context manager, not a coroutine
    mock_session.begin_nested = MagicMock(return_value=_FakeNestedTransaction())

    async def override():
        yield mock_session

    main.app.dependency_overrides[main.get_db] = override
    yield mock_session
    main.app.dependency_overrides.pop(main.get_db, None)
```

### JWT Token Mocking

```python
MANAGER_PAYLOAD = {
    "sub": "user-123",
    "realm_access": {"roles": ["Manager"]},
    "exp": 9999999999,
}

def test_create_nature_success(mock_db):
    # Mock JWT decode
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Camp Biblique", "description": "...", "labels": []},
        )
    assert response.status_code == 201
```

### Mock Object Return Values

```python
def test_create_nature_success(mock_db):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # no duplicate
    mock_db.execute.return_value = mock_result

    async def mock_refresh(obj):
        obj.id = 1
        obj.created_at = datetime(2026, 3, 28, tzinfo=timezone.utc)
        obj.labels = []

    mock_db.refresh.side_effect = mock_refresh
```

### MinIO Client Mocking

```python
def test_request_put_success():
    fake_url = "http://localhost:9000/projects/proj-1/audio/test.mp3?X-Amz-Signature=xyz"

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_put_object", return_value=fake_url):
        response = client.post(
            "/v1/upload/request-put",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"project_id": "proj-1", "filename": "test.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 200
    assert "localhost:9000" in response.json()["presigned_url"]
```

### Test Parametrization (Multiple Roles)

```python
@pytest.mark.parametrize("payload", [MANAGER_PAYLOAD, ADMIN_PAYLOAD, EXPERT_PAYLOAD, TRANSCRIPTEUR_PAYLOAD])
def test_request_get_all_roles_succeed(payload):
    """All 4 roles can get a presigned GET URL."""
    fake_url = "http://localhost:9000/projects/proj-1/audio/test.mp3?X-Amz-Signature=xyz"

    with patch.object(main, "decode_token", return_value=payload), \
         patch.object(main.presigned_client, "presigned_get_object", return_value=fake_url):
        response = client.get(
            "/v1/upload/request-get",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"project_id": "proj-1", "object_key": "projects/proj-1/audio/test.mp3"},
        )
    assert response.status_code == 200
```

### Fake Context Manager for DB Transactions

```python
class _FakeNestedTransaction:
    """Mimics the async context manager returned by session.begin_nested()."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False
```

---

## 7. Key Env Vars & Config

**Location:** `src/api/fastapi/main.py:37–106`

```python
REQUIRED_ENV_VARS = [
    "KEYCLOAK_ISSUER",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_PRESIGNED_ENDPOINT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "CAMUNDA_REST_URL",
]
```

**MinIO Buckets:**
```python
_MINIO_BUCKETS = ["projects", "golden-set", "snapshots", "models"]
_MINIO_REGION = "us-east-1"
```

---

## 8. AudioFileStatus Enum

**Location:** `src/api/fastapi/main.py:149–154`

```python
class AudioFileStatus(str, Enum):
    UPLOADED = "uploaded"        # Initial state after browser upload
    ASSIGNED = "assigned"        # Assigned to transcriber (Story 3.x)
    IN_PROGRESS = "in_progress"  # Transcription in progress
    TRANSCRIBED = "transcribed"  # Transcription complete
    VALIDATED = "validated"      # QA validation passed
```

---

## 9. Helper Function: `_get_wav_duration()`

**Location:** `src/workers/ffmpeg-worker/main.py:121`

Called from FFmpeg worker after successful normalization:

```python
duration_s = await anyio.to_thread.run_sync(_get_wav_duration, output_path)
```

**Implementation detail:** Extracts duration from WAV header (should be implemented in worker).

---

## 10. Database Session Management

**Location:** `src/api/fastapi/main.py:93–102`

```python
POSTGRES_USER: str = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD: str = os.environ["POSTGRES_PASSWORD"]
DATABASE_URL: str = (
    f"postgresql+asyncpg://{quote_plus(POSTGRES_USER)}:{quote_plus(POSTGRES_PASSWORD)}@postgres:5432/zachai"
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

---

## Summary of Key Patterns for Story 2.3

| Pattern | Usage |
|---------|-------|
| **AudioFile Model** | One-to-many with Project; CASCADE delete; track status, paths, duration |
| **FFmpeg Worker** | Request/response model; error codes (413, 422, 504, 500); PCM 16-bit mono 16kHz output |
| **Presigned URLs** | Two MinIO clients (internal + presigned); 1-hour expiry; direct browser upload |
| **Error Handling** | HTTPException with flat `{"error": "..."}` body; role checks first; try-catch MinIO |
| **DB Transactions** | `begin_nested()` for atomic inserts; `IntegrityError` catch for duplicates |
| **Testing** | Mock AsyncSession with `_FakeNestedTransaction`; patch decode_token; patch MinIO methods |
| **Status Transitions** | Enum-based; validate against allowed transitions before update |

---

## File Paths for Reference

- **FastAPI Gateway:** `/D:\zachai\src\api\fastapi\main.py`
- **FastAPI Tests:** `/D:\zachai\src\api\fastapi\test_main.py`
- **FFmpeg Worker:** `/D:\zachai\src\workers\ffmpeg-worker\main.py`
- **Compose:** `/D:\zachai\src\compose.yml`
