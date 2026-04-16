# Story 2.1: CRUD Natures & Schémas de Labels

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Manager,
I can create a project nature (e.g., "Camp Biblique") and configure its label set (e.g., Orateur, Traducteur, Prière),
so that Label Studio can later be provisioned with the correct annotation schema for that nature.

---

## Acceptance Criteria

1. FastAPI reads `POSTGRES_USER` and `POSTGRES_PASSWORD` env vars at startup and connects to PostgreSQL (`zachai` database, internal Docker hostname `postgres:5432`). Connection failure returns a startup warning (not crash) — same tolerant pattern as JWKS. Tables `natures` and `label_schemas` are created automatically via SQLAlchemy `create_all` if they do not exist.

2. `POST /v1/natures` — Auth: Manager or Admin JWT. Body: `{name: str, description: str | null, labels: [{name: str, color: str, is_speech: bool, is_required: bool}]}`. Creates a `Nature` row + associated `LabelSchema` rows in a single transaction. Returns **HTTP 201** with `{id, name, description, created_by, created_at, labels: [...], label_studio_schema: "<View>..."}`. Returns HTTP 400 `{"error": "Nature name already exists"}` if name is duplicate. Returns HTTP 403 if role is Transcripteur or Expert.

3. `GET /v1/natures` — Auth: Manager or Admin. Returns HTTP 200 with list of all natures: `[{id, name, description, created_at, label_count}, ...]`. Empty list `[]` if no natures exist.

4. `GET /v1/natures/{nature_id}` — Auth: Manager or Admin. Returns HTTP 200 with full nature including labels and `label_studio_schema`. Returns HTTP 404 `{"error": "Nature not found"}` if not found.

5. `PUT /v1/natures/{nature_id}/labels` — Auth: Manager or Admin. Body: `{labels: [{name: str, color: str, is_speech: bool, is_required: bool}]}`. Atomically replaces **all** existing labels for this nature (delete-all then insert-new in one transaction). Returns HTTP 200 with updated nature (same shape as POST response). Returns HTTP 404 if nature not found.

6. `label_studio_schema` field: A valid Label Studio XML string generated from the nature's labels. Uses `<AudioPlus>` for the audio track, `<Labels>` for all label values (speech labels first, then non-speech), and `<TextArea>` for transcription input. This XML is used by Camunda 7 in Story 2.2 to provision Label Studio projects.

7. All error responses follow `{"error": "..."}` format — consistent with Story 1.3 custom HTTPException handler (already registered in `main.py`).

8. `src/compose.yml`: `fastapi` service `depends_on` gains `postgres: condition: service_healthy`. `POSTGRES_USER: ${POSTGRES_USER}` and `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}` added to the fastapi environment block. `src/.env.example` notes that FastAPI reuses the existing PostgreSQL credentials.

9. Unit tests: at least 15 tests covering all 5 endpoints, role enforcement (403), not-found (404), duplicate name (400), label replacement, and label_studio_schema XML structure. DB sessions mocked via `AsyncMock`. All tests pass.

---

## Tasks / Subtasks

- [x] **Task 1** — Add SQLAlchemy + asyncpg to `requirements.txt` (AC: 1)
  - [x] Add `sqlalchemy[asyncio]>=2.0.0`
  - [x] Add `asyncpg>=0.29.0`
  - [x] Add `pytest-asyncio>=0.23.0` (for async tests)

- [x] **Task 2** — Define ORM models and DB engine in `main.py` (AC: 1)
  - [x] Add `POSTGRES_USER`, `POSTGRES_PASSWORD` to `REQUIRED_ENV_VARS` list
  - [x] Build `DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@postgres:5432/zachai"`
  - [x] Create `AsyncEngine` with `create_async_engine(DATABASE_URL)`
  - [x] Create `AsyncSessionLocal` with `async_sessionmaker(engine, expire_on_commit=False)`
  - [x] Define `Base`, `Nature` ORM model, `LabelSchema` ORM model (see Dev Notes for exact column spec)
  - [x] Extend lifespan: run `Base.metadata.create_all` in `async with engine.begin()` — tolerant (log error, don't crash on DB failure)
  - [x] Dispose engine in lifespan cleanup (`await engine.dispose()`)
  - [x] Add `get_db` async generator dependency

- [x] **Task 3** — Implement helper function `generate_label_studio_xml` (AC: 6)
  - [x] Pure function: takes `nature_name: str` + `labels: list[LabelSchema]` → returns XML string
  - [x] Speech labels before non-speech in `<Labels>` block
  - [x] See exact XML template in Dev Notes

- [x] **Task 4** — Implement `POST /v1/natures` endpoint (AC: 2)
  - [x] Pydantic request body models: `LabelIn`, `NatureCreateRequest` (include `is_required` in `LabelIn`)
  - [x] Role check: Manager or Admin required (403 otherwise)
  - [x] Duplicate name check → 400
  - [x] Create `Nature` + all `LabelSchema` rows in one transaction (`flush()` to get ID, then `commit()`)
  - [x] Return 201 with full nature shape including `label_studio_schema`

- [x] **Task 5** — Implement `GET /v1/natures` and `GET /v1/natures/{nature_id}` (AC: 3, 4)
  - [x] `GET /v1/natures`: query all natures, return `label_count` (count from subquery or len of eager-loaded labels)
  - [x] `GET /v1/natures/{nature_id}`: eager-load labels, generate `label_studio_schema`, 404 if not found

- [x] **Task 6** — Implement `PUT /v1/natures/{nature_id}/labels` (AC: 5)
  - [x] 404 check first
  - [x] Role check: Manager or Admin
  - [x] Delete all existing `LabelSchema` rows for this nature (`DELETE WHERE nature_id = id`)
  - [x] Insert new labels (including `is_required` value)
  - [x] Commit and return updated nature with schema

- [x] **Task 7** — Update `src/compose.yml` and `src/.env.example` (AC: 8)
  - [x] Add `postgres: condition: service_healthy` to fastapi `depends_on`
  - [x] Add `POSTGRES_USER: ${POSTGRES_USER}` and `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}` to fastapi `environment`
  - [x] In `.env.example`, add comment in FastAPI section: `# POSTGRES_USER/PASSWORD already defined in PostgreSQL section above — FastAPI reuses them`

- [x] **Task 8** — Write unit tests in `test_main.py` (AC: 9)
  - [x] Mock `AsyncSession` and `engine` at module level
  - [x] Test POST /v1/natures success (201), duplicate (400), wrong role (403), missing token (401)
  - [x] Test GET /v1/natures (200 list), GET /v1/natures/{id} (200 and 404)
  - [x] Test PUT /v1/natures/{id}/labels (200, 404, wrong role)
  - [x] Test label_studio_schema XML contains expected tags
  - [x] All existing 17 tests must still pass (no regressions)

---

## Dev Notes

### Critical: This Story Extends `main.py` — Do NOT Rewrite It

`src/api/fastapi/main.py` already has:
- `validate_env()` — add `POSTGRES_USER`, `POSTGRES_PASSWORD` to `REQUIRED_ENV_VARS` list
- `@app.exception_handler(HTTPException)` — already returns flat `{"error": "..."}` — reuse, do not duplicate
- `get_current_user`, `get_roles`, `decode_token` — reuse these dependencies unchanged
- `_bearer_scheme`, `lifespan`, `app` — extend lifespan, do not replace it

**File to modify:** `src/api/fastapi/main.py` — add ORM models, DB engine, 5 new endpoints.
**File to modify:** `src/api/fastapi/requirements.txt` — add sqlalchemy + asyncpg.
**File to modify:** `src/api/fastapi/test_main.py` — add 15+ new tests, keep all existing 17.
**File to modify:** `src/compose.yml` — add postgres dependency + env vars to fastapi service.
**File to modify:** `src/.env.example` — add note about PostgreSQL creds reuse.
**Do NOT modify:** `src/config/postgres/init.sql` — already creates the `zachai` database (Story 1.2).

### PostgreSQL Connection (Docker Internal Network)

```python
# New env vars — add to REQUIRED_ENV_VARS list
REQUIRED_ENV_VARS = [
    "KEYCLOAK_ISSUER", "MINIO_ENDPOINT", "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY", "MINIO_PRESIGNED_ENDPOINT",
    "POSTGRES_USER", "POSTGRES_PASSWORD",   # ← add these
]

# Module-level DB config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, func, select, delete

POSTGRES_USER: str = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD: str = os.environ["POSTGRES_PASSWORD"]
DATABASE_URL: str = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@postgres:5432/zachai"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

**`pool_pre_ping=True`** — validates connections before use (handles postgres restarts).

**DB hostname:** `postgres` — Docker internal DNS (not `localhost`, not `127.0.0.1`). Port `5432`. Database `zachai`.

### ORM Models — Exact Spec

```python
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Nature(Base):
    __tablename__ = "natures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)  # sub (UUID) from JWT
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    labels: Mapped[list["LabelSchema"]] = relationship(
        "LabelSchema", cascade="all, delete-orphan", lazy="selectin"
    )

class LabelSchema(Base):
    __tablename__ = "label_schemas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nature_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("natures.id", ondelete="CASCADE"), nullable=False
    )
    label_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label_color: Mapped[str] = mapped_column(String(20), nullable=False)   # hex color e.g. "#FF5733"
    is_speech: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

### Lifespan Extension

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _jwks_cache
    # JWKS (existing)
    try:
        _jwks_cache = await fetch_jwks(KEYCLOAK_ISSUER)
        logger.info("JWKS loaded: %d key(s)", len(_jwks_cache.get("keys", [])))
    except Exception as exc:
        logger.error("Failed to load JWKS: %s", exc)

    # DB tables (new)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized")
    except Exception as exc:
        logger.error("Failed to initialize DB tables: %s — DB operations will fail", exc)

    yield

    await engine.dispose()
```

### DB Dependency

```python
from typing import AsyncGenerator

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

### Pydantic Request/Response Models

```python
from pydantic import Field

class LabelIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    color: str = Field(..., pattern=r"^#[0-9A-Fa-f]{3,6}$")  # Hex color validation
    is_speech: bool = True
    is_required: bool = False

class NatureCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    labels: list[LabelIn]

class LabelsUpdateRequest(BaseModel):
    labels: list[LabelIn]
```

### Label Studio XML Schema Generation

```python
def generate_label_studio_xml(labels: list[LabelSchema]) -> str:
    """Generate Label Studio labeling interface XML from a nature's label set.
    Speech labels appear first; non-speech (Pause, Bruit, Musique) follow.
    This XML is stored in the GET/POST response and consumed by Camunda 7 in Story 2.2.
    """
    speech = [l for l in labels if l.is_speech]
    non_speech = [l for l in labels if not l.is_speech]

    label_tags = "\n".join(
        f'    <Label value="{l.label_name}" background="{l.label_color}"/>'
        for l in speech + non_speech
    )

    return f"""<View>
  <AudioPlus name="audio" value="$audio"/>
  <Labels name="label" toName="audio">
{label_tags}
  </Labels>
  <TextArea name="transcription" toName="audio" rows="4" editable="true" placeholder="Transcription..."/>
</View>"""
```

### Response Shape Helper

```python
def _nature_to_dict(nature: Nature) -> dict:
    return {
        "id": nature.id,
        "name": nature.name,
        "description": nature.description,
        "created_by": nature.created_by,
        "created_at": nature.created_at.isoformat(),
        "labels": [
            {
                "id": l.id,
                "name": l.label_name,
                "color": l.label_color,
                "is_speech": l.is_speech,
                "is_required": l.is_required,
            }
            for l in nature.labels
        ],
        "label_studio_schema": generate_label_studio_xml(nature.labels),
    }
```

### Endpoint Implementations — Key Logic

**POST /v1/natures:**
```python
@app.post("/v1/natures", status_code=201)
async def create_nature(
    body: NatureCreateRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    # Duplicate check
    result = await db.execute(select(Nature).where(Nature.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail={"error": "Nature name already exists"})

    nature = Nature(name=body.name, description=body.description, created_by=payload["sub"])
    db.add(nature)
    await db.flush()  # populate nature.id before label inserts

    for label in body.labels:
        db.add(LabelSchema(
            nature_id=nature.id,
            label_name=label.name,
            label_color=label.color,
            is_speech=label.is_speech,
            is_required=label.is_required,
        ))

    await db.commit()
    await db.refresh(nature)
    return _nature_to_dict(nature)
```

**PUT /v1/natures/{nature_id}/labels:**
```python
@app.put("/v1/natures/{nature_id}/labels")
async def update_nature_labels(
    nature_id: int,
    body: LabelsUpdateRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    result = await db.execute(select(Nature).where(Nature.id == nature_id))
    nature = result.scalar_one_or_none()
    if not nature:
        raise HTTPException(status_code=404, detail={"error": "Nature not found"})

    # Atomic replace: delete all then insert new
    await db.execute(delete(LabelSchema).where(LabelSchema.nature_id == nature_id))
    for label in body.labels:
        db.add(LabelSchema(
            nature_id=nature_id,
            label_name=label.name,
            label_color=label.color,
            is_speech=label.is_speech,
            is_required=label.is_required,
        ))

    await db.commit()
    # Reload with fresh labels (selectin loading via relationship)
    result = await db.execute(select(Nature).where(Nature.id == nature_id))
    nature = result.scalar_one()
    return _nature_to_dict(nature)
```

### compose.yml Changes

Add to the existing `fastapi` service (do not change other services):

```yaml
fastapi:
  # ... existing config ...
  environment:
    # ... existing env vars ...
    POSTGRES_USER: ${POSTGRES_USER}         # ← add
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD} # ← add
  depends_on:
    keycloak:
      condition: service_healthy
    minio:
      condition: service_healthy
    postgres:                               # ← add
      condition: service_healthy
```

### Testing Strategy — Mocking AsyncSession

SQLAlchemy async sessions require careful mocking. Do NOT mock at the SQLAlchemy engine level — override the `get_db` FastAPI dependency instead:

```python
from unittest.mock import AsyncMock, MagicMock, patch

# Create a mock session factory
def test_create_nature_success():
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock execute for duplicate check (None = not found)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    # Nature mock after refresh
    mock_nature = MagicMock()
    mock_nature.id = 1
    mock_nature.name = "Camp Biblique"
    mock_nature.description = None
    mock_nature.created_by = "user-123"
    mock_nature.created_at = datetime(2026, 3, 28, tzinfo=timezone.utc)
    mock_nature.labels = []

    async def mock_refresh(obj):
        # Simulate SQLAlchemy refreshing the nature object
        pass
    mock_session.refresh = mock_refresh

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        # Note: use AsyncClient (httpx) for async endpoints in tests
        response = client.post("/v1/natures", json={...})

    app.dependency_overrides.clear()  # Always clean up
```

**IMPORTANT:** Call `app.dependency_overrides.clear()` after each test (or use a fixture). Leaving overrides active will pollute subsequent tests.

**Alternative (simpler):** Use `pytest` fixtures with `autouse=False` and `app.dependency_overrides`:

```python
@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock(spec=AsyncSession)
    async def override():
        yield mock_session
    app.dependency_overrides[main.get_db] = override
    yield mock_session
    app.dependency_overrides.pop(main.get_db, None)
```

### Label Studio XML — Expected Format

Story 2.2 (Camunda 7 workers) will POST this XML verbatim to Label Studio's project creation API. Validate that the generated XML is well-formed:

```xml
<View>
  <AudioPlus name="audio" value="$audio"/>
  <Labels name="label" toName="audio">
    <Label value="Orateur" background="#FF5733"/>
    <Label value="Traducteur" background="#33FF57"/>
    <Label value="Pause" background="#999999"/>
    <Label value="Bruit / Parasite" background="#555555"/>
  </Labels>
  <TextArea name="transcription" toName="audio" rows="4" editable="true" placeholder="Transcription..."/>
</View>
```

Key requirements:
- `<AudioPlus>` not `<Audio>` — Label Studio uses AudioPlus for segmented audio annotation
- `name="audio"`, `value="$audio"` — the `$audio` variable is set by Label Studio from the task data
- `toName="audio"` on both `<Labels>` and `<TextArea>` — must match the AudioPlus name
- Speech labels first, then non-speech labels (based on `is_speech` field)

### Port & Service Context

Current compose.yml ports (do NOT conflict):

| Port | Service |
|------|---------|
| 9000 | MinIO S3 API |
| 9001 | MinIO Console |
| 9002 | Keycloak Management |
| 8180 | Keycloak UI + OIDC |
| 8000 | FastAPI Gateway |
| 5432 | PostgreSQL (internal only) |
| 8765 | FFmpeg Worker (internal only) |

FastAPI is the only service on port 8000. PostgreSQL port 5432 is internal-only (not mapped to host in current compose.yml — that's correct).

### PostgreSQL DB Already Exists

`src/config/postgres/init.sql` (Story 1.2) already creates the `zachai` database:
```sql
SELECT 'CREATE DATABASE zachai' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'zachai')\gexec
```

Story 2.1 does NOT need to modify `init.sql`. SQLAlchemy `create_all` will create the `natures` and `label_schemas` tables inside the `zachai` database at FastAPI startup.

### Camunda 7 — NOT in this Story

Story 2.1 scope: pure CRUD for Nature + LabelSchema. **Do NOT add Camunda 7 calls.** The `label_studio_schema` XML field is generated and returned in the API response for Camunda workers to use in Story 2.2. FastAPI does not call Camunda or Label Studio in this story.

### Error Handling Pattern (from Story 1.3)

The custom exception handler is already registered in `main.py`:
```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    body = detail if isinstance(detail, dict) else {"error": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=body)
```

All new endpoints MUST raise `HTTPException(status_code=..., detail={"error": "..."})` with a dict — not a string. This ensures the flat `{"error": "..."}` format.

### SQLAlchemy Async Import Pattern

```python
# Add to imports in main.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, func, select, delete
from typing import AsyncGenerator
from datetime import datetime
```

`AsyncGenerator` is imported from `typing` (already imported for `Annotated`). Check that `datetime` isn't already imported — it is used by `timedelta` import already.

### Previous Story Patterns (Story 1.3) — Must Follow

- **YAML 2-space indentation** in compose.yml
- **Env var validation at module load**: fail fast via `validate_env()` — add new vars to the list
- **Pydantic BaseModel** for request bodies (already used for `PutRequestBody`)
- **`Annotated[AsyncSession, Depends(get_db)]`** pattern — consistent with `Annotated[dict, Depends(get_current_user)]`
- **Error format:** `{"error": "..."}` — never `{"detail": "..."}`
- **No hardcoded credentials** in code

---

## Translation Note (French / Traduction)

**Résumé de la Story 2.1 :**
Cette story ajoute la **couche de données métier** à ZachAI. Le FastAPI Gateway se connecte désormais à PostgreSQL (base `zachai`) et expose un CRUD complet pour les **Natures** (types de projets) et leurs **Schémas de Labels**.

**Pourquoi "Nature" ?** Une Nature est un template de projet (ex: "Camp Biblique", "Témoignage"). Elle définit dynamiquement les labels disponibles pour l'annotation dans Label Studio. Le Manager crée les natures une seule fois — tous les projets de cette nature héritent du même schéma de labels.

**Pourquoi le XML Label Studio ?** Le champ `label_studio_schema` est le pont vers Story 2.2. En Story 2.2, Camunda 7 appellera l'API Label Studio avec ce XML pour créer automatiquement le projet d'annotation. FastAPI ne contacte pas Camunda ni Label Studio dans cette story — il se contente de stocker et de générer le schéma XML.

**Dépendances nouvelle de FastAPI :** SQLAlchemy 2.x + asyncpg pour l'accès async à PostgreSQL. FastAPI doit maintenant dépendre de `postgres: condition: service_healthy` dans `compose.yml`.

---

## References

- Natures & Labels CRUD: [Source: docs/api-mapping.md § 2 — Gestion des Projets & Natures]
- DB schema `Nature` + `LabelSchema`: [Source: docs/architecture.md § 3 — Modèle de Données Métier]
- Label Studio provisioning context: [Source: docs/prd.md § 3.2 — Nature Dynamique]
- Label Studio XML format: [Source: docs/prd.md § 3.3 — Labels Dynamiques + § 4.4]
- FastAPI as lean Gateway (no binary data): [Source: docs/architecture.md § 1.B]
- Docker startup order (fastapi depends postgres): [Source: docs/architecture.md § 6 — Docker Compose Ordre de Démarrage]
- `zachai` database already created: [Source: src/config/postgres/init.sql]
- Error format `{"error": "..."}`: [Source: src/api/fastapi/main.py — http_exception_handler]

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (2026-03-28)

### Debug Log References

- SQLAlchemy/asyncpg not installed in local Python environment — installed via pip before running tests.

### Completion Notes List

- Extended `main.py` with SQLAlchemy 2.x async ORM: `Nature` + `LabelSchema` models, `AsyncEngine`, `AsyncSessionLocal`, `get_db` dependency.
- Added 5 new REST endpoints: `POST /v1/natures`, `GET /v1/natures`, `GET /v1/natures/{id}`, `PUT /v1/natures/{id}/labels`, plus `generate_label_studio_xml` and `_nature_to_dict` helpers.
- Lifespan extended with tolerant `Base.metadata.create_all` + `engine.dispose()` on shutdown.
- `POSTGRES_USER` + `POSTGRES_PASSWORD` added to `REQUIRED_ENV_VARS` and module-level config.
- `compose.yml` updated: fastapi service now depends on `postgres: condition: service_healthy`; postgres env vars added to fastapi environment block.
- `.env.example` updated with comment about credential reuse.
- `requirements.txt`: added `sqlalchemy[asyncio]>=2.0.0`, `asyncpg>=0.29.0`, `pytest-asyncio>=0.23.0`.
- `test_main.py`: 17 new tests (34 total). All 34 pass, zero regressions. DB session mocked via `mock_db` pytest fixture using `app.dependency_overrides`.

### File List

- `src/api/fastapi/main.py` — extended with SQLAlchemy ORM, DB engine, get_db, 5 Nature endpoints, helpers
- `src/api/fastapi/requirements.txt` — added sqlalchemy[asyncio], asyncpg, pytest-asyncio
- `src/api/fastapi/test_main.py` — added 17 new tests (34 total, all passing)
- `src/compose.yml` — added postgres dependency + POSTGRES env vars to fastapi service
- `src/.env.example` — added comment about PostgreSQL credential reuse for FastAPI

### Change Log

- 2026-03-28: Story 2.1 implemented — Nature CRUD API with SQLAlchemy async ORM, Label Studio XML generation, 34 tests passing.

---

### Review Findings

- [x] [Review][Patch] XML Injection in Label Studio schema generation [src/api/fastapi/main.py:270]
- [x] [Review][Patch] Database connection URL fails if credentials contain special characters [src/api/fastapi/main.py:101-103]
- [x] [Review][Patch] Label update pattern is destructive and lacks transaction safety [src/api/fastapi/main.py:431]
- [x] [Review][Patch] Audit trail fallback to "unknown" compromises accountability [src/api/fastapi/main.py:412]
- [x] [Review][Patch] Hex color validation regex is incomplete [src/api/fastapi/main.py:236]
- [x] [Review][Patch] created_by field missing from GET /v1/natures response [src/api/fastapi/main.py:421-427]
- [x] [Review][Patch] Potential race condition between check and reload [src/api/fastapi/main.py:441]
- [x] [Review][Patch] Duplicate label names allowed within the same Nature [src/api/fastapi/main.py:384]
- [x] [Review][Patch] Test helpers shadow built-in id() [src/api/fastapi/test_main.py]
- [x] [Review][Defer] N+1 query pattern in list view — deferred, pre-existing
- [x] [Review][Defer] Repeated role authorization logic across endpoints — deferred, pre-existing
- [x] [Review][Defer] Brittle database initialization (Alembic missing) — deferred, pre-existing

---

### Review Findings (Pass 2)

- [x] [Review][Patch] TOCTOU Race Condition on Nature Name uniqueness [src/api/fastapi/main.py:398]
- [x] [Review][Patch] Missing max_length validation for Nature description in Pydantic model [src/api/fastapi/main.py:255]
- [x] [Review][Defer] Missing Health Check DB probe — deferred, story scope
- [x] [Review][Defer] Lack of Pagination on Nature list — deferred, scalability
- [x] [Review][Defer] Manual validation loops refactoring — deferred, maintainability
- [x] [Review][Defer] Use URL.create for DB string — deferred, pre-existing
- [x] [Review][Defer] Over-mocked models in unit tests — deferred, test strategy
