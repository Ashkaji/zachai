"""
ZachAI FastAPI Gateway — Story 2.4: Assignment dashboard + FFmpeg semantics fix
Extends Story 2.3: Audio upload + FFmpeg normalization (success leaves status `uploaded` + `normalized_path`).
Adds: Assignment ORM, project status/assign endpoints, transcripteur task list, optional project audio summary.
FastAPI never touches audio binary data — upload goes directly browser→MinIO.
"""
import os
import uuid
import logging
import html
from contextlib import asynccontextmanager
from datetime import timedelta, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, AsyncGenerator
from urllib.parse import quote_plus

import httpx
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload
from sqlalchemy import String, Boolean, Integer, Float, ForeignKey, DateTime, func, select, delete, Index, case
from sqlalchemy import UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.exc import IntegrityError
from lxml import etree

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Env var validation ───────────────────────────────────────────────────────

REQUIRED_ENV_VARS = [
    "KEYCLOAK_ISSUER",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_PRESIGNED_ENDPOINT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "CAMUNDA_REST_URL",
    "FFMPEG_WORKER_URL",
]

ALLOWED_GET_PREFIXES = ("projects/", "golden-set/", "snapshots/")


def validate_env() -> None:
    """Fail fast if any required environment variable is missing or empty."""
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


# ─── Module-level config ──────────────────────────────────────────────────────

validate_env()

KEYCLOAK_ISSUER: str = os.environ["KEYCLOAK_ISSUER"]
MINIO_SECURE: bool = os.environ.get("MINIO_SECURE", "false").lower() == "true"
MINIO_INTERNAL_ENDPOINT: str = os.environ["MINIO_ENDPOINT"]
MINIO_PRESIGNED_ENDPOINT: str = os.environ["MINIO_PRESIGNED_ENDPOINT"]

# MinIO project buckets — region cache is pre-seeded to avoid SDK network call on presign.
# MinIO uses "us-east-1" as its default region for all buckets.
_MINIO_BUCKETS = ["projects", "golden-set", "snapshots", "models"]
_MINIO_REGION = "us-east-1"

# Internal client — connects to minio:9000 (Docker network) for admin ops.
internal_client = Minio(
    endpoint=MINIO_INTERNAL_ENDPOINT,
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=MINIO_SECURE,
)

# Presigned URL client — uses the externally reachable endpoint (localhost:9000).
# Region cache is pre-seeded so the SDK generates signed URLs without making any network call.
presigned_client = Minio(
    endpoint=MINIO_PRESIGNED_ENDPOINT,
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,  # localhost is never TLS in dev
)
presigned_client._region_map = {bucket: _MINIO_REGION for bucket in _MINIO_BUCKETS}

# JWKS cache — populated at startup, avoids per-request Keycloak calls
_jwks_cache: dict = {}

# ─── PostgreSQL / SQLAlchemy ──────────────────────────────────────────────────

POSTGRES_USER: str = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD: str = os.environ["POSTGRES_PASSWORD"]
DATABASE_URL: str = (
    f"postgresql+asyncpg://{quote_plus(POSTGRES_USER)}:{quote_plus(POSTGRES_PASSWORD)}@postgres:5432/zachai"
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ─── Camunda 7 REST client ──────────────────────────────────────────────────

CAMUNDA_REST_URL: str = os.environ["CAMUNDA_REST_URL"]
FFMPEG_WORKER_URL: str = os.environ["FFMPEG_WORKER_URL"].rstrip("/")

camunda_client = httpx.AsyncClient(base_url=CAMUNDA_REST_URL, timeout=30.0)

# FFmpeg worker HTTP client — created in lifespan (real AsyncClient; tests avoid import-time mock issues)
_ffmpeg_client: httpx.AsyncClient | None = None


# ─── ORM Models ───────────────────────────────────────────────────────────────


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
    label_color: Mapped[str] = mapped_column(String(20), nullable=False)
    is_speech: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"


class AudioFileStatus(str, Enum):
    UPLOADED = "uploaded"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    TRANSCRIBED = "transcribed"
    VALIDATED = "validated"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Name must be unique across all projects (enforced by explicit index in __table_args__)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # RESTRICT cascade: Natures are immutable once projects reference them. Prevents accidental
    # deletion of nature definitions that could orphan projects. If archival is needed in future
    # stories, add soft-delete (is_deleted flag) to Nature table rather than loosening this constraint.
    nature_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("natures.id", ondelete="RESTRICT"), nullable=False
    )
    production_goal: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus), default=ProjectStatus.DRAFT, nullable=False
    )
    manager_id: Mapped[str] = mapped_column(String(255), nullable=False)
    process_instance_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label_studio_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Explicitly define unique index on name for clarity and performance
    __table_args__ = (Index("ix_projects_name_unique", "name", unique=True),)

    nature: Mapped["Nature"] = relationship("Nature", lazy="selectin")
    audio_files: Mapped[list["AudioFile"]] = relationship(
        "AudioFile", cascade="all, delete-orphan", lazy="selectin"
    )


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
    validation_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    validation_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audio_files_project_status", "project_id", "status"),
        UniqueConstraint("project_id", "minio_path", name="uq_audio_files_project_minio_path"),
    )

    assignment: Mapped["Assignment | None"] = relationship(
        "Assignment",
        back_populates="audio_file",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Assignment(Base):
    """At most one active assignment row per audio (Story 2.4)."""

    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    transcripteur_id: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manager_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    audio_file: Mapped["AudioFile"] = relationship("AudioFile", back_populates="assignment")


# ─── JWKS fetch ───────────────────────────────────────────────────────────────


async def fetch_jwks(issuer: str) -> dict:
    """Fetch public JWKS from Keycloak at startup. Cached for lifetime of process."""
    jwks_url = f"{issuer}/protocol/openid-connect/certs"
    logger.info("Fetching JWKS from %s", jwks_url)
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


# ─── BPMN deployment ─────────────────────────────────────────────────────────


async def deploy_bpmn_workflows() -> None:
    """Deploy BPMN workflows to Camunda 7 at startup. Tolerant — logs on failure."""
    try:
        # Try multiple paths for both local dev (src/api/fastapi/main.py) and Docker (/app/main.py)
        potential_paths = [
            Path(__file__).parent.parent.parent / "bpmn" / "project-lifecycle.bpmn",  # local dev
            Path(__file__).parent / "bpmn" / "project-lifecycle.bpmn",               # Docker /app/bpmn
            Path("/bpmn/project-lifecycle.bpmn"),                                    # Alternative mount
        ]
        
        bpmn_file = None
        for p in potential_paths:
            if p.exists():
                bpmn_file = p
                break

        if not bpmn_file:
            logger.warning("BPMN file not found in potential paths — workflows not deployed")
            return

        logger.info("Deploying BPMN workflow from: %s", bpmn_file)
        with open(bpmn_file, "rb") as f:
            files = {"data": (bpmn_file.name, f)}
            data = {"deployment-name": "zachai-workflows", "enable-duplicate-filtering": "true"}
            resp = await camunda_client.post("/deployment/create", files=files, data=data)

        if 200 <= resp.status_code < 300:
            logger.info("BPMN workflows deployed to Camunda 7")
        else:
            logger.error("Failed to deploy BPMN: %s %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.error("Exception deploying BPMN workflows: %s", exc)


# ─── Application lifespan ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _jwks_cache, _ffmpeg_client
    # JWKS (existing) — tolerant: Keycloak may still be starting
    try:
        _jwks_cache = await fetch_jwks(KEYCLOAK_ISSUER)
        logger.info("JWKS loaded: %d key(s)", len(_jwks_cache.get("keys", [])))
    except Exception as exc:
        logger.error(
            "Failed to load JWKS from Keycloak: %s — JWT verification will fail until Keycloak is reachable",
            exc,
        )

    # DB tables — tolerant: PostgreSQL may not be ready yet.
    # create_all creates only missing tables; it does not migrate existing schemas.
    # Brownfield DBs: apply SQL DDL manually for new columns, indexes, and constraints
    # (e.g. Story 2.3 audio_files validation_* columns; Story 2.4 `assignments` table;
    # see story Dev Agent Record / Completion Notes for DDL).
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized")
    except Exception as exc:
        logger.error(
            "Failed to initialize DB tables: %s — DB operations will fail", exc
        )

    # BPMN deployment — tolerant: Camunda may not be ready yet
    await deploy_bpmn_workflows()

    # FFmpeg worker — internal HTTP client (Story 2.3)
    _ffmpeg_client = httpx.AsyncClient(base_url=FFMPEG_WORKER_URL, timeout=120.0)
    try:
        hr = await _ffmpeg_client.get("/health", timeout=5.0)
        if hr.status_code != 200:
            logger.warning("FFmpeg worker /health returned HTTP %s", hr.status_code)
    except Exception as exc:
        logger.warning("FFmpeg worker unreachable at startup — audio normalization may fail: %s", exc)

    yield

    if _ffmpeg_client is not None:
        await _ffmpeg_client.aclose()
        _ffmpeg_client = None
    await engine.dispose()
    await camunda_client.aclose()


app = FastAPI(
    title="ZachAI Gateway",
    description="Lean API gateway: presigned URLs, JWT, Nature CRUD, Project CRUD, audio upload, Camunda 7",
    version="2.4.0",
    lifespan=lifespan,
)

# ─── Security ─────────────────────────────────────────────────────────────────


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


_bearer_scheme = HTTPBearer(auto_error=False)


def decode_token(token: str) -> dict:
    """
    Decode and verify a Keycloak JWT using cached JWKS.
    Raises HTTPException 401 on invalid/expired token.
    """
    try:
        payload = jwt.decode(
            token,
            _jwks_cache,
            algorithms=["RS256"],
            options={"verify_aud": False},  # realm-level roles — no audience claim to verify
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"error": "Token expired"})
    except JWTError:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})


def get_roles(payload: dict) -> list[str]:
    """Extract Keycloak realm roles from JWT payload."""
    return payload.get("realm_access", {}).get("roles", [])


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> dict:
    """FastAPI dependency: extract and verify Bearer JWT, return decoded payload."""
    if credentials is None:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})
    return decode_token(credentials.credentials)


# ─── DB Dependency ────────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ─── Schemas ──────────────────────────────────────────────────────────────────


class PutRequestBody(BaseModel):
    project_id: str
    filename: str
    content_type: str


class LabelIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    color: str = Field(..., pattern=r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")
    is_speech: bool = True
    is_required: bool = False


class NatureCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    labels: list[LabelIn]


class LabelsUpdateRequest(BaseModel):
    labels: list[LabelIn]


VALID_PRODUCTION_GOALS = {"livre", "sous-titres", "dataset", "archive"}


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    nature_id: int
    production_goal: str = Field(
        ..., pattern=r"^(livre|sous-titres|dataset|archive)$"
    )


class StatusUpdateRequest(BaseModel):
    status: str


class AudioUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=128)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("filename cannot be empty or whitespace only")
        if s != v:
            raise ValueError("filename has leading or trailing whitespace")
        if any(c in s for c in r'\/:*?"<>|'):
            raise ValueError("filename contains forbidden characters")
        if any(ord(c) < 32 for c in s):
            raise ValueError("filename contains control characters")
        if "." not in s or s.endswith("."):
            raise ValueError("filename must include a file extension")
        return s


class AudioRegisterRequest(BaseModel):
    object_key: str = Field(..., min_length=1, max_length=512)

    @field_validator("object_key")
    @classmethod
    def strip_object_key(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("object_key cannot be empty")
        return s


class AssignAudioRequest(BaseModel):
    audio_id: int = Field(..., gt=0)
    transcripteur_id: str = Field(..., min_length=1, max_length=255)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def generate_label_studio_xml(labels: list) -> str:
    """Generate Label Studio labeling interface XML from a nature's label set.
    Speech labels appear first; non-speech (Pause, Bruit, Musique) follow.
    This XML is consumed by Camunda 7 in Story 2.2 to provision Label Studio projects.
    """
    speech = [lb for lb in labels if lb.is_speech]
    non_speech = [lb for lb in labels if not lb.is_speech]

    label_tags = "\n".join(
        f'    <Label value="{html.escape(lb.label_name)}" background="{html.escape(lb.label_color)}"/>'
        for lb in speech + non_speech
    )

    return (
        "<View>\n"
        '  <AudioPlus name="audio" value="$audio"/>\n'
        '  <Labels name="label" toName="audio">\n'
        f"{label_tags}\n"
        "  </Labels>\n"
        '  <TextArea name="transcription" toName="audio" rows="4" editable="true" placeholder="Transcription..."/>\n'
        "</View>"
    )


def _nature_to_dict(nature: Nature) -> dict:
    return {
        "id": nature.id,
        "name": nature.name,
        "description": nature.description,
        "created_by": nature.created_by,
        "created_at": nature.created_at.isoformat(),
        "labels": [
            {
                "id": lb.id,
                "name": lb.label_name,
                "color": lb.label_color,
                "is_speech": lb.is_speech,
                "is_required": lb.is_required,
            }
            for lb in nature.labels
        ],
        "label_studio_schema": generate_label_studio_xml(nature.labels),
    }


def _project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "nature_id": project.nature_id,
        "nature_name": project.nature.name,
        "production_goal": project.production_goal,
        "status": project.status.value,
        "manager_id": project.manager_id,
        "process_instance_id": project.process_instance_id,
        "label_studio_project_id": project.label_studio_project_id,
        "created_at": project.created_at.isoformat(),
        "labels": [
            {
                "id": lb.id,
                "name": lb.label_name,
                "color": lb.label_color,
                "is_speech": lb.is_speech,
                "is_required": lb.is_required,
            }
            for lb in project.nature.labels
        ],
        "audio_files": [
            {
                "id": af.id,
                "filename": af.filename,
                "status": af.status.value,
                "normalized_path": af.normalized_path,
                "validation_error": af.validation_error,
                "uploaded_at": af.uploaded_at.isoformat(),
            }
            for af in project.audio_files
        ],
    }


ALLOWED_STATUS_TRANSITIONS = {
    "draft": ["active"],
    "active": ["completed"],
    "completed": [],
}


def _require_manager_or_admin(roles: list[str]) -> None:
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})


def _require_project_owner_or_admin(project: Project, payload: dict, roles: list[str]) -> None:
    """Manager must own the project; Admin bypasses (Story 2.4)."""
    if "Admin" in roles:
        return
    if "Manager" not in roles:
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})
    sub = payload.get("sub")
    if not sub or project.manager_id != sub:
        raise HTTPException(status_code=403, detail={"error": "Not the project owner"})


def _audio_normalized_eligible(af: AudioFile) -> bool:
    return af.normalized_path is not None and af.validation_error is None


def _assign_state_blocks_reassign(af: AudioFile) -> bool:
    """409 when human workflow has moved past assignment (Story 2.4 AC4 optional)."""
    return af.status in (AudioFileStatus.TRANSCRIBED, AudioFileStatus.VALIDATED)


def _ensure_project_accepts_audio(project: Project) -> None:
    if project.status not in (ProjectStatus.DRAFT, ProjectStatus.ACTIVE):
        raise HTTPException(
            status_code=403,
            detail={"error": "Project must be in draft or active status to accept audio files"},
        )


def _parse_bucket_and_object(full_key: str) -> tuple[str, str]:
    parts = full_key.strip().split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail={"error": "Invalid object key format"})
    return parts[0], parts[1]


def _normalized_object_name(object_name: str) -> str:
    p = Path(object_name)
    return str(p.with_name(f"{p.stem}.normalized.wav"))


def _parse_duration_s(dur: object) -> float | None:
    """Parse FFmpeg worker duration_s; never raises (invalid values → None, logged)."""
    if dur is None:
        return None
    try:
        return float(dur)
    except (TypeError, ValueError):
        logger.warning("Invalid duration_s from FFmpeg worker: %r", dur)
        return None


def _worker_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            return str(data["error"])
    except Exception:
        pass
    return resp.text or "FFmpeg worker error"


def _audio_file_to_dict(af: AudioFile) -> dict:
    return {
        "id": af.id,
        "project_id": af.project_id,
        "filename": af.filename,
        "minio_path": af.minio_path,
        "normalized_path": af.normalized_path,
        "duration_s": af.duration_s,
        "status": af.status.value,
        "validation_error": af.validation_error,
        "validation_attempted_at": (
            af.validation_attempted_at.isoformat() if af.validation_attempted_at else None
        ),
        "uploaded_at": af.uploaded_at.isoformat(),
        "updated_at": af.updated_at.isoformat(),
    }


def _audio_row_for_project_status(af: AudioFile) -> dict:
    row = _audio_file_to_dict(af)
    asg = af.assignment
    row["assigned_to"] = asg.transcripteur_id if asg else None
    row["assigned_at"] = asg.assigned_at.isoformat() if asg else None
    return row


async def call_ffmpeg_normalize(db: AsyncSession, audio: AudioFile) -> None:
    """Drive FFmpeg worker /normalize; updates audio row. Raises HTTPException on transport failure."""
    global _ffmpeg_client
    if _ffmpeg_client is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "FFmpeg service unavailable, retry later"},
        )

    bucket, object_name = _parse_bucket_and_object(audio.minio_path)
    out_obj = _normalized_object_name(object_name)
    req_body = {
        "input_bucket": bucket,
        "input_key": object_name,
        "output_bucket": bucket,
        "output_key": out_obj,
    }

    audio.status = AudioFileStatus.IN_PROGRESS
    audio.validation_attempted_at = datetime.now(timezone.utc)
    audio.validation_error = None
    await db.commit()
    await db.refresh(audio)

    try:
        resp = await _ffmpeg_client.post("/normalize", json=req_body)
    except httpx.RequestError as exc:
        logger.error("FFmpeg worker request error audio_id=%s: %s", audio.id, exc)
        audio.status = AudioFileStatus.UPLOADED
        audio.validation_error = "FFmpeg service unavailable, retry later"
        audio.validation_attempted_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail={"error": "FFmpeg service unavailable, retry later"},
        )

    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception:
            data = {}
        if data.get("status") != "ok":
            err = _worker_error_message(resp)[:1024]
            audio.status = AudioFileStatus.UPLOADED
            audio.validation_error = err
            audio.validation_attempted_at = datetime.now(timezone.utc)
            await db.commit()
            raise HTTPException(status_code=500, detail={"error": err})
        out_key = data.get("output_key", out_obj)
        dur = data.get("duration_s")
        # PRD human lifecycle: `transcribed` is after transcripteur work, not after FFmpeg.
        audio.status = AudioFileStatus.UPLOADED
        audio.normalized_path = f"{bucket}/{out_key}"
        audio.duration_s = _parse_duration_s(dur)
        audio.validation_error = None
        await db.commit()
        return

    err = _worker_error_message(resp)[:1024]
    audio.status = AudioFileStatus.UPLOADED
    audio.validation_error = err
    audio.validation_attempted_at = datetime.now(timezone.utc)
    await db.commit()

    if resp.status_code == 413:
        raise HTTPException(status_code=413, detail={"error": err})
    if resp.status_code == 422:
        raise HTTPException(status_code=422, detail={"error": err})
    raise HTTPException(
        status_code=500,
        detail={"error": "FFmpeg service unavailable, retry later"},
    )


# ─── Routes — Presigned URLs (Story 1.3) ─────────────────────────────────────


@app.get("/health")
def health() -> dict:
    """Docker healthcheck endpoint — unauthenticated."""
    return {"status": "ok"}


@app.post("/v1/upload/request-put")
def request_put(
    body: PutRequestBody,
    payload: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Generate a presigned MinIO PUT URL for audio upload.
    Requires Manager role. File goes directly browser→MinIO — never through FastAPI.
    """
    roles = get_roles(payload)
    if "Manager" not in roles:
        raise HTTPException(status_code=403, detail={"error": "Manager role required"})

    # object_name = key within the 'projects' bucket (no bucket prefix)
    object_name = f"{body.project_id}/audio/{body.filename}"
    # object_key = full path including bucket, for use with request-get
    object_key = f"projects/{object_name}"

    try:
        presigned_url = presigned_client.presigned_put_object(
            bucket_name="projects",
            object_name=object_name,
            expires=timedelta(hours=1),
        )
    except Exception as exc:
        logger.error("MinIO presigned_put_object failed: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Failed to generate upload URL"})

    return {
        "presigned_url": presigned_url,
        "object_key": object_key,
        "expires_in": 3600,
    }


@app.get("/v1/upload/request-get")
def request_get(
    payload: Annotated[dict, Depends(get_current_user)],
    project_id: str = Query(..., description="Project identifier"),
    object_key: str = Query(
        ...,
        description="MinIO object key (must start with 'projects/', 'golden-set/', or 'snapshots/')",
    ),
) -> dict:
    """
    Generate a presigned MinIO GET URL for audio access.
    Requires any authenticated role (Admin / Manager / Transcripteur / Expert).
    Object key must be scoped to authorized buckets to prevent path traversal.
    """
    roles = get_roles(payload)
    valid_roles = {"Admin", "Manager", "Transcripteur", "Expert"}
    if not valid_roles.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Authenticated role required"})

    # Path traversal / scope protection: only allow reads from authorized bucket prefixes
    if not object_key.startswith(ALLOWED_GET_PREFIXES):
        raise HTTPException(status_code=403, detail={"error": "Invalid object key scope"})

    try:
        presigned_url = presigned_client.presigned_get_object(
            bucket_name=object_key.split("/")[0],  # derive bucket from key prefix
            object_name="/".join(object_key.split("/")[1:]),  # object path within bucket
            expires=timedelta(hours=1),
        )
    except Exception as exc:
        logger.error("MinIO presigned_get_object failed: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Failed to generate download URL"})

    return {
        "presigned_url": presigned_url,
        "expires_in": 3600,
    }


# ─── Routes — Nature CRUD (Story 2.1) ────────────────────────────────────────


@app.post("/v1/natures", status_code=201)
async def create_nature(
    body: NatureCreateRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    if len({lb.name for lb in body.labels}) != len(body.labels):
        raise HTTPException(status_code=400, detail={"error": "Duplicate label names provided"})

    creator_id = payload.get("sub", payload.get("preferred_username"))
    if not creator_id:
        raise HTTPException(status_code=401, detail={"error": "Creator identifier missing in token"})

    try:
        async with db.begin_nested():
            nature = Nature(
                name=body.name,
                description=body.description,
                created_by=creator_id,
            )
            db.add(nature)
            await db.flush()  # populate nature.id before label inserts

            for label in body.labels:
                db.add(
                    LabelSchema(
                        nature_id=nature.id,
                        label_name=label.name,
                        label_color=label.color,
                        is_speech=label.is_speech,
                        is_required=label.is_required,
                    )
                )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # This covers both the duplicate Nature name and any potential LabelSchema conflicts
        raise HTTPException(status_code=400, detail={"error": "Nature name already exists or data integrity violation"})

    await db.refresh(nature)
    return _nature_to_dict(nature)


@app.get("/v1/natures")
async def list_natures(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    result = await db.execute(select(Nature))
    natures = result.scalars().all()
    return [
        {
            "id": n.id,
            "name": n.name,
            "description": n.description,
            "created_by": n.created_by,
            "created_at": n.created_at.isoformat(),
            "label_count": len(n.labels),
        }
        for n in natures
    ]


@app.get("/v1/natures/{nature_id}")
async def get_nature(
    nature_id: int,
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

    return _nature_to_dict(nature)


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

    if len({lb.name for lb in body.labels}) != len(body.labels):
        raise HTTPException(status_code=400, detail={"error": "Duplicate label names provided"})

    result = await db.execute(select(Nature).where(Nature.id == nature_id))
    nature = result.scalar_one_or_none()
    if not nature:
        raise HTTPException(status_code=404, detail={"error": "Nature not found"})

    # Atomic replace: delete all existing labels then insert new ones
    async with db.begin_nested():
        await db.execute(delete(LabelSchema).where(LabelSchema.nature_id == nature_id))
        for label in body.labels:
            db.add(
                LabelSchema(
                    nature_id=nature_id,
                    label_name=label.name,
                    label_color=label.color,
                    is_speech=label.is_speech,
                    is_required=label.is_required,
                )
            )

    await db.commit()
    # Expire to force reload of labels relationship in the next select
    db.expire(nature)
    # Reload with fresh labels (selectin loading via relationship)
    result = await db.execute(select(Nature).where(Nature.id == nature_id))
    nature = result.scalar_one_or_none()
    if not nature:
        raise HTTPException(status_code=404, detail={"error": "Nature was concurrently deleted"})
    return _nature_to_dict(nature)


# ─── Routes — Project CRUD (Story 2.2) ─────────────────────────────────────


@app.post("/v1/projects", status_code=201)
async def create_project(
    body: ProjectCreateRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    # Check nature exists
    result = await db.execute(select(Nature).where(Nature.id == body.nature_id))
    nature = result.scalar_one_or_none()
    if not nature:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Nature {body.nature_id} not found"},
        )

    creator_id = payload.get("sub", payload.get("preferred_username"))
    if not creator_id:
        raise HTTPException(status_code=401, detail={"error": "Creator identifier missing in token"})

    # Validate label schema BEFORE creating project to avoid orphaned projects with invalid schemas
    label_schema_xml = generate_label_studio_xml(nature.labels)
    try:
        etree.fromstring(label_schema_xml.encode())
    except etree.XMLSyntaxError as xml_err:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Generated label schema is invalid XML: {str(xml_err)}"},
        )

    try:
        async with db.begin_nested():
            project = Project(
                name=body.name,
                description=body.description,
                nature_id=body.nature_id,
                production_goal=body.production_goal,
                manager_id=creator_id,
                status=ProjectStatus.DRAFT,
            )
            db.add(project)
            await db.flush()  # populate project.id

        # Start Camunda process (don't fail project creation if unavailable)
        try:

            variables = {
                "projectId": {"value": project.id, "type": "Integer"},
                "natureName": {"value": nature.name, "type": "String"},
                "labelStudioSchema": {"value": label_schema_xml, "type": "String"},
                "projectStatus": {"value": "draft", "type": "String"},
            }
            resp = await camunda_client.post(
                "/process-definition/key/project-lifecycle/start",
                json={"variables": variables, "withVariablesInReturn": True},
            )
            if 200 <= resp.status_code < 300:
                camunda_data = resp.json()
                process_id = camunda_data.get("id")
                if not process_id:
                    logger.error(
                        "Camunda response missing 'id' field: %s — project created but workflow not triggered",
                        camunda_data,
                    )
                else:
                    project.process_instance_id = process_id
                    logger.info("Camunda process started: %s", project.process_instance_id)
            else:
                logger.error(
                    "Camunda start failed: %s — project created but workflow not triggered",
                    resp.status_code,
                )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as exc:
            logger.error(
                "Camunda unavailable (network error): %s — project created but workflow not triggered",
                exc,
            )

        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail={"error": "Project name already exists"})

    await db.refresh(project)
    return _project_to_dict(project)


@app.get("/v1/projects")
async def list_projects(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include: str | None = Query(
        None,
        description='Pass "audio_summary" for per-project audio counts (single aggregate query; no N+1).',
    ),
) -> list:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    result = await db.execute(select(Project).options(selectinload(Project.nature)))
    projects = result.scalars().all()

    counts_by_project: dict[int, dict[str, int]] = {}
    unassigned_by_project: dict[int, int] = {}
    if include == "audio_summary":
        agg = await db.execute(
            select(
                AudioFile.project_id,
                func.sum(case((AudioFile.status == AudioFileStatus.UPLOADED, 1), else_=0)).label(
                    "uploaded"
                ),
                func.sum(case((AudioFile.status == AudioFileStatus.ASSIGNED, 1), else_=0)).label(
                    "assigned"
                ),
                func.sum(case((AudioFile.status == AudioFileStatus.IN_PROGRESS, 1), else_=0)).label(
                    "in_progress"
                ),
                func.sum(case((AudioFile.status == AudioFileStatus.TRANSCRIBED, 1), else_=0)).label(
                    "transcribed"
                ),
                func.sum(case((AudioFile.status == AudioFileStatus.VALIDATED, 1), else_=0)).label(
                    "validated"
                ),
            ).group_by(AudioFile.project_id)
        )
        for r in agg.all():
            pid = int(r.project_id)
            counts_by_project[pid] = {
                "uploaded": int(r.uploaded or 0),
                "assigned": int(r.assigned or 0),
                "in_progress": int(r.in_progress or 0),
                "transcribed": int(r.transcribed or 0),
                "validated": int(r.validated or 0),
            }
        un_rows = await db.execute(
            select(AudioFile.project_id, func.count(AudioFile.id))
            .outerjoin(Assignment, Assignment.audio_id == AudioFile.id)
            .where(
                AudioFile.normalized_path.isnot(None),
                AudioFile.validation_error.is_(None),
                Assignment.id.is_(None),
            )
            .group_by(AudioFile.project_id)
        )
        for pid, c in un_rows.all():
            unassigned_by_project[int(pid)] = int(c)

    out: list[dict] = []
    for p in projects:
        base = {
            "id": p.id,
            "name": p.name,
            "nature_name": p.nature.name,
            "status": p.status.value,
            "manager_id": p.manager_id,
            "created_at": p.created_at.isoformat(),
        }
        if include == "audio_summary":
            base["audio_counts_by_status"] = counts_by_project.get(
                p.id,
                {
                    "uploaded": 0,
                    "assigned": 0,
                    "in_progress": 0,
                    "transcribed": 0,
                    "validated": 0,
                },
            )
            base["unassigned_normalized_count"] = unassigned_by_project.get(p.id, 0)
        out.append(base)
    return out


@app.get("/v1/projects/{project_id}")
async def get_project(
    project_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})

    return _project_to_dict(project)


@app.put("/v1/projects/{project_id}/status")
async def update_project_status(
    project_id: int,
    body: StatusUpdateRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})

    new_status = body.status
    valid_values = {s.value for s in ProjectStatus}
    if new_status not in valid_values:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Invalid status: {new_status}"},
        )

    current = project.status.value
    if new_status not in ALLOWED_STATUS_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=400,
            detail={"error": f"Cannot transition from {current} to {new_status}"},
        )

    project.status = ProjectStatus(new_status)
    await db.commit()
    await db.refresh(project)
    return _project_to_dict(project)


# ─── Routes — Assignment dashboard (Story 2.4) ───────────────────────────────


@app.get("/v1/projects/{project_id}/status")
async def get_project_dashboard_status(
    project_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Project audio rows with assignee metadata; Manager owner or Admin."""
    roles = get_roles(payload)
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.audio_files).selectinload(AudioFile.assignment))
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    _require_project_owner_or_admin(project, payload, roles)

    audios = [_audio_row_for_project_status(af) for af in project.audio_files]
    return {
        "project_status": project.status.value,
        "audios": audios,
    }


@app.post("/v1/projects/{project_id}/assign")
async def assign_audio_to_transcripteur(
    project_id: int,
    body: AssignAudioRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Create/update Assignment for an audio; Manager owner or Admin."""
    roles = get_roles(payload)
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    _require_project_owner_or_admin(project, payload, roles)

    result = await db.execute(
        select(AudioFile)
        .where(AudioFile.id == body.audio_id, AudioFile.project_id == project_id)
        .options(selectinload(AudioFile.assignment))
    )
    audio = result.scalar_one_or_none()
    if not audio:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if _assign_state_blocks_reassign(audio):
        raise HTTPException(
            status_code=409,
            detail={"error": "Cannot reassign audio after transcription or validation"},
        )
    if audio.status == AudioFileStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail={"error": "Audio normalization in progress"},
        )
    if not _audio_normalized_eligible(audio):
        raise HTTPException(
            status_code=400,
            detail={"error": "Audio is not assignable until normalized without errors"},
        )

    asg = audio.assignment
    now = datetime.now(timezone.utc)
    if asg:
        asg.transcripteur_id = body.transcripteur_id
        asg.assigned_at = now
    else:
        db.add(
            Assignment(
                audio_id=audio.id,
                transcripteur_id=body.transcripteur_id,
                assigned_at=now,
            )
        )
    audio.status = AudioFileStatus.ASSIGNED
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": "Assignment conflict, retry the request"},
        )
    await db.refresh(audio)
    result = await db.execute(
        select(AudioFile)
        .where(AudioFile.id == audio.id)
        .options(selectinload(AudioFile.assignment))
    )
    audio = result.scalar_one()
    return _audio_row_for_project_status(audio)


@app.get("/v1/me/audio-tasks")
async def list_my_audio_tasks(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    transcripteur_id: str | None = Query(
        None,
        description="Admin-only override to inspect another transcripteur's tasks.",
    ),
) -> list:
    """Audios assigned to the caller (Transcripteur); Admin may list for support/debug."""
    roles = get_roles(payload)
    if "Admin" not in roles and "Transcripteur" not in roles:
        raise HTTPException(status_code=403, detail={"error": "Transcripteur or Admin role required"})
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})

    target_sub = sub
    if "Admin" in roles and transcripteur_id:
        target_sub = transcripteur_id

    stmt = (
        select(Assignment, AudioFile, Project)
        .join(AudioFile, Assignment.audio_id == AudioFile.id)
        .join(Project, AudioFile.project_id == Project.id)
        .where(Assignment.transcripteur_id == target_sub)
        .order_by(Assignment.assigned_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "audio_id": af.id,
            "project_id": proj.id,
            "project_name": proj.name,
            "filename": af.filename,
            "status": af.status.value,
            "assigned_at": asg.assigned_at.isoformat(),
        }
        for asg, af, proj in rows
    ]


# ─── Routes — Audio upload & FFmpeg (Story 2.3) ─────────────────────────────


@app.post("/v1/projects/{project_id}/audio-files/upload")
async def request_project_audio_upload(
    project_id: int,
    body: AudioUploadRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    _require_manager_or_admin(roles)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    _ensure_project_accepts_audio(project)

    ct = body.content_type.lower()
    if not (ct.startswith("audio/") or ct.startswith("video/")):
        raise HTTPException(
            status_code=400,
            detail={"error": "content_type must be audio/* or video/*"},
        )

    ext = Path(body.filename).suffix
    if ext:
        ext = ext.lower().lstrip(".")
    else:
        ext = "bin"
    unique = uuid.uuid4().hex
    object_name = f"{project_id}/audio/{unique}.{ext}"
    object_key = f"projects/{object_name}"

    try:
        presigned_url = presigned_client.presigned_put_object(
            bucket_name="projects",
            object_name=object_name,
            expires=timedelta(hours=1),
        )
    except Exception as exc:
        logger.error("MinIO presigned_put_object failed: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Failed to generate upload URL"})

    return {
        "object_key": object_key,
        "presigned_url": presigned_url,
        "expires_in": 3600,
    }


@app.post("/v1/projects/{project_id}/audio-files/register", status_code=201)
async def register_project_audio_file(
    project_id: int,
    body: AudioRegisterRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    _require_manager_or_admin(roles)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    _ensure_project_accepts_audio(project)

    expected_prefix = f"projects/{project_id}/audio/"
    if not body.object_key.startswith(expected_prefix):
        raise HTTPException(
            status_code=400,
            detail={"error": f"object_key must start with {expected_prefix}"},
        )

    bucket, object_name = _parse_bucket_and_object(body.object_key)
    if bucket != "projects":
        raise HTTPException(status_code=400, detail={"error": "Invalid bucket for audio object_key"})

    try:
        internal_client.stat_object(bucket, object_name)
    except S3Error as exc:
        code = getattr(exc, "code", None) or ""
        if code == "NoSuchKey":
            raise HTTPException(
                status_code=400,
                detail={"error": "Object not found in storage"},
            )
        logger.error("MinIO stat_object failed for %s/%s: %s", bucket, object_name, exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "Storage error while verifying object"},
        )

    filename = Path(object_name).name
    audio = AudioFile(
        project_id=project_id,
        filename=filename,
        minio_path=body.object_key,
        status=AudioFileStatus.UPLOADED,
    )
    db.add(audio)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"error": "Audio file already registered for this object key"},
        )

    await db.refresh(audio)
    await call_ffmpeg_normalize(db, audio)
    await db.refresh(audio)
    return _audio_file_to_dict(audio)


@app.post("/v1/projects/{project_id}/audio-files/{audio_file_id}/normalize")
async def normalize_project_audio_on_demand(
    project_id: int,
    audio_file_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    roles = get_roles(payload)
    _require_manager_or_admin(roles)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    _ensure_project_accepts_audio(project)

    result = await db.execute(
        select(AudioFile).where(
            AudioFile.id == audio_file_id,
            AudioFile.project_id == project_id,
        )
    )
    audio = result.scalar_one_or_none()
    if not audio:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})
    if audio.status != AudioFileStatus.UPLOADED:
        raise HTTPException(
            status_code=400,
            detail={"error": "Audio file must be in uploaded status to normalize"},
        )

    await call_ffmpeg_normalize(db, audio)
    await db.refresh(audio)
    return _audio_file_to_dict(audio)
