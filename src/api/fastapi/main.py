"""
ZachAI FastAPI Gateway — Story 4.1–4.4: Golden Set + LoRA pipeline
Extends Story 2.4: Assignment dashboard + FFmpeg semantics fix.
Golden Set: POST /v1/golden-set/entry, frontend-correction, expert webhook; Story 5.2: POST /v1/editor/ticket (Redis WSS handshake); threshold crossing starts `lora-fine-tuning` BPMN (Story 4.3–4.4).
POST /v1/callback/model-ready resets counter after successful registry publish (Story 4.4).
FastAPI never touches audio binary data — upload goes directly browser→MinIO.
"""
import os
import io
import uuid
import hmac
import math
import logging
import html
import time
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
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload
from sqlalchemy import String, Boolean, Integer, Float, ForeignKey, DateTime, Text, LargeBinary, func, select, delete, Index, case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.exc import IntegrityError
from lxml import etree

import golden_set
import editor_ticket

import redis.asyncio as redis_asyncio

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
    "REDIS_URL",
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

# Golden Set bucket (Story 4.1) — must exist (minio-init); default matches architecture.
GOLDEN_SET_BUCKET: str = (os.environ.get("GOLDEN_SET_BUCKET") or "golden-set").strip() or "golden-set"
_raw_threshold = os.environ.get("GOLDEN_SET_THRESHOLD", "1000")
try:
    GOLDEN_SET_THRESHOLD: int = int(_raw_threshold)
except (TypeError, ValueError):
    logger.warning("GOLDEN_SET_THRESHOLD=%r is not a valid integer; falling back to 1000", _raw_threshold)
    GOLDEN_SET_THRESHOLD: int = 1000

# Camunda process definition key for LoRA pipeline orchestration (Story 4.3; PRD §4.6)
LORA_FINETUNING_PROCESS_KEY: str = "lora-fine-tuning"

# Shared secrets — cached at startup (Story 4.1)
_LABEL_STUDIO_WEBHOOK_SECRET: str = (os.environ.get("LABEL_STUDIO_WEBHOOK_SECRET") or "").strip()
_GOLDEN_SET_INTERNAL_SECRET: str = (os.environ.get("GOLDEN_SET_INTERNAL_SECRET") or "").strip()
_MODEL_READY_CALLBACK_SECRET: str = (os.environ.get("MODEL_READY_CALLBACK_SECRET") or "").strip()
_CHANGEME_PREFIXES = ("changeme",)
if _LABEL_STUDIO_WEBHOOK_SECRET and _LABEL_STUDIO_WEBHOOK_SECRET.startswith(_CHANGEME_PREFIXES):
    logger.warning("LABEL_STUDIO_WEBHOOK_SECRET uses a default 'changeme' value — override in production")
if _GOLDEN_SET_INTERNAL_SECRET and _GOLDEN_SET_INTERNAL_SECRET.startswith(_CHANGEME_PREFIXES):
    logger.warning("GOLDEN_SET_INTERNAL_SECRET uses a default 'changeme' value — override in production")
if _MODEL_READY_CALLBACK_SECRET and _MODEL_READY_CALLBACK_SECRET.startswith(_CHANGEME_PREFIXES):
    logger.warning("MODEL_READY_CALLBACK_SECRET uses a default 'changeme' value — override in production")

_GOLDEN_SET_ACTIONS = frozenset({"ANNOTATION_CREATED", "ANNOTATION_UPDATED", "ANNOTATION_SUBMITTED"})

# FFmpeg worker HTTP client — created in lifespan (real AsyncClient; tests avoid import-time mock issues)
_ffmpeg_client: httpx.AsyncClient | None = None

# Redis — WSS editor tickets (Story 5.2); optional at runtime if ping fails (mint → 503)
_redis_client: redis_asyncio.Redis | None = None


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


class GoldenSetEntry(Base):
    """One row per golden-set artifact (PostgreSQL) + matching MinIO JSON object (Story 4.1)."""

    __tablename__ = "golden_set_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False
    )
    segment_start: Mapped[float] = mapped_column(Float, nullable=False)
    segment_end: Mapped[float] = mapped_column(Float, nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_text: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    minio_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    label_studio_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_studio_annotation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_golden_set_entry_idempotency"),
        Index("ix_golden_set_entries_audio_id", "audio_id"),
    )


class GoldenSetCounter(Base):
    __tablename__ = "golden_set_counters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    last_training_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class YjsLog(Base):
    """Binary Yjs document state chunks per audio document (Story 5.1 — architecture §3)."""

    __tablename__ = "yjs_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False
    )
    update_binary: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_yjs_logs_document_id_id", "document_id", "id"),)


class ModelReadyIdempotency(Base):
    """One row per successful model-ready callback (Story 4.4) — dedupes worker retries."""

    __tablename__ = "model_ready_idempotency"
    training_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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

_BPMN_DEPLOY_NAMES: tuple[str, ...] = ("project-lifecycle.bpmn", "lora-fine-tuning.bpmn")


async def deploy_bpmn_workflows() -> None:
    """Deploy BPMN workflows to Camunda 7 at startup. Tolerant — logs on failure."""
    try:
        potential_dirs = [
            Path(__file__).parent.parent.parent / "bpmn",
            Path(__file__).parent / "bpmn",
            Path("/bpmn"),
        ]
        bpmn_dir: Path | None = None
        for d in potential_dirs:
            if (d / "project-lifecycle.bpmn").exists():
                bpmn_dir = d
                break

        if not bpmn_dir:
            logger.warning("BPMN directory not found in potential paths — workflows not deployed")
            return

        bpmn_paths = [bpmn_dir / name for name in _BPMN_DEPLOY_NAMES if (bpmn_dir / name).exists()]
        if not bpmn_paths:
            logger.warning("No BPMN files found under %s", bpmn_dir)
            return

        logger.info("Deploying BPMN workflows from %s: %s", bpmn_dir, [p.name for p in bpmn_paths])
        file_handles: list = []
        try:
            multipart: list = []
            for p in bpmn_paths:
                fh = open(p, "rb")
                file_handles.append(fh)
                multipart.append(("data", (p.name, fh, "application/xml")))
            data = {"deployment-name": "zachai-workflows", "enable-duplicate-filtering": "true"}
            resp = await camunda_client.post("/deployment/create", files=multipart, data=data)
        finally:
            for fh in file_handles:
                fh.close()

        if 200 <= resp.status_code < 300:
            logger.info("BPMN workflows deployed to Camunda 7")
        else:
            logger.error("Failed to deploy BPMN: %s %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.error("Exception deploying BPMN workflows: %s", exc)


# ─── Application lifespan ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _jwks_cache, _ffmpeg_client, _redis_client
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
        async with AsyncSessionLocal() as session:
            async with session.begin():
                r = await session.execute(select(GoldenSetCounter).where(GoldenSetCounter.id == 1))
                if r.scalar_one_or_none() is None:
                    session.add(
                        GoldenSetCounter(id=1, count=0, threshold=GOLDEN_SET_THRESHOLD)
                    )
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

    # Redis — Story 5.2 (WSS tickets). Tolerant startup: ticket endpoint returns 503 if down.
    _redis_url = (os.environ.get("REDIS_URL") or "").strip()
    if _redis_url:
        try:
            _redis_client = redis_asyncio.from_url(_redis_url, decode_responses=True)
            await _redis_client.ping()
            logger.info("Redis connected (WSS editor tickets)")
        except Exception as exc:
            logger.error(
                "Redis unavailable at startup — POST /v1/editor/ticket will return 503 until Redis is reachable: %s",
                exc,
            )
            _redis_client = None
    else:
        logger.error("REDIS_URL empty — POST /v1/editor/ticket will return 503")
        _redis_client = None

    yield

    if _ffmpeg_client is not None:
        await _ffmpeg_client.aclose()
        _ffmpeg_client = None
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    await engine.dispose()
    await camunda_client.aclose()


app = FastAPI(
    title="ZachAI Gateway",
    description="Lean API gateway: presigned URLs, JWT, Nature CRUD, Project CRUD, audio upload, Golden Set, Camunda 7",
    version="2.10.0",
    lifespan=lifespan,
)

# ─── CORS (Story 4.2 — frontend runs on different port in dev) ────────────
from fastapi.middleware.cors import CORSMiddleware

_CORS_ORIGINS = [
    o.strip()
    for o in (os.environ.get("CORS_ALLOWED_ORIGINS") or "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


def _validation_errors_json_safe(errors: list) -> list:
    """Make Pydantic RequestValidationError payloads JSON-serializable (ctx may hold Exception objects)."""

    def _clean(obj: object) -> object:
        if isinstance(obj, dict):
            return {str(k): _clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_clean(item) for item in obj]
        if isinstance(obj, BaseException):
            return str(obj)
        return obj

    return [_clean(e) for e in errors]


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
        content={"detail": _validation_errors_json_safe(errors)},
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


class GoldenSetEntryRequest(BaseModel):
    """Internal ingest contract — see docs/api-mapping.md §4."""

    audio_id: int = Field(..., gt=0)
    segment_start: float = Field(..., ge=0)
    segment_end: float = Field(..., ge=0)
    corrected_text: str = Field("", max_length=50000)
    label: str | None = Field(None, max_length=512)
    source: str = Field(..., max_length=64)
    weight: str = Field(..., max_length=32)
    original_text: str | None = Field(None, max_length=50000)
    idempotency_key: str | None = Field(None, max_length=128)
    label_studio_task_id: int | None = None
    label_studio_annotation_id: int | None = None

    @field_validator("segment_start", "segment_end")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("segment boundaries must be finite numbers")
        return v

    @model_validator(mode="after")
    def _start_le_end(self) -> "GoldenSetEntryRequest":
        if self.segment_start > self.segment_end:
            raise ValueError("segment_start must be <= segment_end")
        return self

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in ("label_studio", "frontend_correction"):
            raise ValueError("source must be label_studio or frontend_correction")
        return v

    @field_validator("weight")
    @classmethod
    def _weight(cls, v: str) -> str:
        if v not in ("high", "standard"):
            raise ValueError("weight must be high or standard")
        return v


class GoldenSetStatusResponse(BaseModel):
    """GET /v1/golden-set/status — Story 4.3."""

    count: int = Field(..., ge=0)
    threshold: int
    last_training_at: str | None = Field(
        None, description="Set when a training run completes (Story 4.4); null until then."
    )
    next_trigger_at: str | None = Field(
        None,
        description="Reserved for future scheduler semantics; always null in Story 4.3.",
    )


class ModelReadyCallbackRequest(BaseModel):
    """POST /v1/callback/model-ready — LoRA registry worker (Story 4.4)."""

    model_version: str = Field(..., min_length=1, max_length=512)
    wer_score: float = Field(..., description="Word error rate on eval split (0–1, jiwer).")
    minio_path: str = Field(..., min_length=1, max_length=1024)
    training_run_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Camunda process instance id (or unique run id) for callback idempotency.",
    )


class FrontendCorrectionRequest(BaseModel):
    """Browser-facing Golden Set capture (Story 4.2 AC1). Server forces source/weight."""

    audio_id: int = Field(..., gt=0)
    segment_start: float = Field(..., ge=0)
    segment_end: float = Field(..., ge=0)
    original_text: str = Field(..., min_length=1, max_length=50000)
    corrected_text: str = Field(..., min_length=1, max_length=50000)
    label: str | None = Field(None, max_length=512)
    client_mutation_id: str | None = Field(None, max_length=128)

    @field_validator("segment_start", "segment_end")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("segment boundaries must be finite numbers")
        return v

    @model_validator(mode="after")
    def _start_le_end(self) -> "FrontendCorrectionRequest":
        if self.segment_start > self.segment_end:
            raise ValueError("segment_start must be <= segment_end")
        return self


_EDITOR_TICKET_PERMISSIONS = frozenset({"read", "write"})


class EditorTicketRequest(BaseModel):
    """POST /v1/editor/ticket — Story 5.2. document_id is AudioFile.id (same as audio_id elsewhere)."""

    document_id: int = Field(..., gt=0)
    permissions: list[str] = Field(..., min_length=1, max_length=16)

    @field_validator("permissions")
    @classmethod
    def _permissions_allowed(cls, v: list[str]) -> list[str]:
        for p in v:
            if p not in _EDITOR_TICKET_PERMISSIONS:
                raise ValueError("each permission must be read or write")
        return v


class EditorTicketResponse(BaseModel):
    ticket_id: str
    ttl: int = Field(default=60, description="Seconds until Redis key expires (Story 5.2).")


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


def _default_golden_idempotency_key(body: GoldenSetEntryRequest) -> str:
    parts = {
        "audio_id": body.audio_id,
        "s0": body.segment_start,
        "s1": body.segment_end,
        "t": body.corrected_text,
        "label": body.label,
        "source": body.source,
        "weight": body.weight,
        "lst": body.label_studio_task_id,
        "lsa": body.label_studio_annotation_id,
    }
    return golden_set.idempotency_key_from_parts(parts)


def _verify_shared_secret(
    request: Request,
    *,
    expected_secret: str,
    header_name: str,
    unconfigured_msg: str,
) -> None:
    """Constant-time shared-secret verification (Story 4.1 AC2). Supports custom header or Bearer."""
    if not expected_secret:
        raise HTTPException(status_code=503, detail={"error": unconfigured_msg})
    header_secret = request.headers.get(header_name)
    bearer = request.headers.get("Authorization") or ""
    bearer_token = bearer[7:].strip() if bearer.startswith("Bearer ") else None
    candidates: list[str] = [c for c in (header_secret, bearer_token) if c]
    if not candidates:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})
    if not any(hmac.compare_digest(c.encode("utf-8"), expected_secret.encode("utf-8")) for c in candidates):
        raise HTTPException(status_code=403, detail={"error": "Forbidden"})


def verify_label_studio_webhook_secret(request: Request) -> None:
    _verify_shared_secret(
        request,
        expected_secret=_LABEL_STUDIO_WEBHOOK_SECRET,
        header_name="X-ZachAI-Webhook-Secret",
        unconfigured_msg="Expert validation webhook is not configured",
    )


def verify_golden_set_internal_secret(request: Request) -> None:
    _verify_shared_secret(
        request,
        expected_secret=_GOLDEN_SET_INTERNAL_SECRET,
        header_name="X-ZachAI-Golden-Set-Internal-Secret",
        unconfigured_msg="Golden set internal API is not configured",
    )


def verify_model_ready_callback_secret(request: Request) -> None:
    _verify_shared_secret(
        request,
        expected_secret=_MODEL_READY_CALLBACK_SECRET,
        header_name="X-ZachAI-Model-Ready-Secret",
        unconfigured_msg="Model-ready callback is not configured",
    )


async def start_lora_finetuning_camunda(golden_set_count: int, threshold: int) -> None:
    """
    POST /process-definition/key/lora-fine-tuning/start — fire-and-forget for ingest path (Story 4.3).
    Logs failures; never raises to callers.
    """
    path = f"/process-definition/key/{LORA_FINETUNING_PROCESS_KEY}/start"
    triggered_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    variables = {
        "goldenSetCount": {"value": golden_set_count, "type": "Integer"},
        "threshold": {"value": threshold, "type": "Integer"},
        "triggeredAt": {"value": triggered_at, "type": "String"},
    }
    try:
        resp = await camunda_client.post(
            path,
            json={"variables": variables, "withVariablesInReturn": True},
        )
        if 200 <= resp.status_code < 300:
            body = resp.json()
            proc_id = body.get("id")
            logger.info(
                "golden_set_lora_camunda_start_ok golden_set_count=%s threshold=%s process_key=%s "
                "camunda_status=%s process_instance_id=%s",
                golden_set_count,
                threshold,
                LORA_FINETUNING_PROCESS_KEY,
                resp.status_code,
                proc_id,
            )
        else:
            logger.error(
                "golden_set_lora_camunda_start_http_error golden_set_count=%s threshold=%s process_key=%s "
                "camunda_status=%s process_instance_id=%s",
                golden_set_count,
                threshold,
                LORA_FINETUNING_PROCESS_KEY,
                resp.status_code,
                None,
            )
    except Exception as exc:
        logger.error(
            "golden_set_lora_camunda_start_error golden_set_count=%s threshold=%s process_key=%s "
            "camunda_status=%s process_instance_id=%s",
            golden_set_count,
            threshold,
            LORA_FINETUNING_PROCESS_KEY,
            type(exc).__name__,
            None,
        )


async def persist_golden_set_entry(
    db: AsyncSession,
    body: GoldenSetEntryRequest,
    *,
    label_studio_project_id_for_verify: int | None = None,
) -> dict:
    """
    Durable Golden Set ingest: idempotent DB row + MinIO JSON + counter increment (Story 4.1).
    On a real increment, may start Camunda `lora-fine-tuning` when threshold is newly crossed (Story 4.3).
    """
    t0 = time.perf_counter()
    ik = (body.idempotency_key or "").strip() or _default_golden_idempotency_key(body)

    dup = await db.execute(select(GoldenSetEntry.id).where(GoldenSetEntry.idempotency_key == ik))
    if dup.scalar_one_or_none() is not None:
        ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "golden_set audio_id=%s task_id=%s entries_written=0 idempotency_hit=1 minio_key=- duration_ms=%.0f",
            body.audio_id,
            body.label_studio_task_id,
            ms,
        )
        return {"status": "ok", "idempotent": True, "idempotency_key": ik, "minio_object_key": None}

    r = await db.execute(select(AudioFile).where(AudioFile.id == body.audio_id))
    af = r.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if label_studio_project_id_for_verify is not None:
        pr = await db.execute(
            select(Project).where(Project.label_studio_project_id == label_studio_project_id_for_verify)
        )
        proj = pr.scalar_one_or_none()
        if proj is not None and proj.id != af.project_id:
            raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    ts_prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    entry_uuid = uuid.uuid4().hex[:12]
    object_rel = f"{body.audio_id}/{ts_prefix}_{entry_uuid}.json"
    core_payload = {
        "audio_id": body.audio_id,
        "segment_start": body.segment_start,
        "segment_end": body.segment_end,
        "original_text": body.original_text,
        "corrected_text": body.corrected_text,
        "label": body.label,
        "source": body.source,
        "weight": body.weight,
        "label_studio_task_id": body.label_studio_task_id,
        "label_studio_annotation_id": body.label_studio_annotation_id,
        "idempotency_key": ik,
    }
    canonical_core = golden_set.canonical_json_bytes(core_payload)
    digest = golden_set.sha256_hex(canonical_core)
    artifact_obj = {**core_payload, "sha256": digest}
    artifact_bytes = golden_set.canonical_json_bytes(artifact_obj)

    try:
        internal_client.put_object(
            GOLDEN_SET_BUCKET,
            object_rel,
            io.BytesIO(artifact_bytes),
            length=len(artifact_bytes),
            content_type="application/json",
            metadata={"sha256": digest},
        )
    except Exception as exc:
        logger.error("golden_set MinIO put_object failed audio_id=%s: %s", body.audio_id, exc)
        raise HTTPException(status_code=500, detail={"error": "Storage error during golden set write"})

    minio_key = f"{GOLDEN_SET_BUCKET}/{object_rel}"
    should_start_lora = False
    lora_new_count = 0
    lora_threshold = 0
    try:
        entry = GoldenSetEntry(
            audio_id=body.audio_id,
            segment_start=body.segment_start,
            segment_end=body.segment_end,
            original_text=body.original_text,
            corrected_text=body.corrected_text,
            label=body.label,
            source=body.source,
            weight=body.weight,
            idempotency_key=ik,
            minio_object_key=minio_key,
            sha256_hex=digest,
            label_studio_task_id=body.label_studio_task_id,
            label_studio_annotation_id=body.label_studio_annotation_id,
        )
        db.add(entry)

        cr = await db.execute(
            select(GoldenSetCounter).where(GoldenSetCounter.id == 1).with_for_update()
        )
        ctr = cr.scalar_one_or_none()
        if ctr is None:
            try:
                ctr = GoldenSetCounter(id=1, count=0, threshold=GOLDEN_SET_THRESHOLD)
                db.add(ctr)
                await db.flush()
            except IntegrityError:
                await db.rollback()
                cr2 = await db.execute(
                    select(GoldenSetCounter).where(GoldenSetCounter.id == 1).with_for_update()
                )
                ctr = cr2.scalar_one()
                db.add(entry)

        previous_count = int(ctr.count)
        db_threshold = int(ctr.threshold)
        new_count = previous_count + 1
        ctr.count = new_count
        if db_threshold <= 0:
            logger.warning(
                "golden_set_lora_skip_non_positive_threshold golden_set_count=%s threshold=%s process_key=%s",
                new_count,
                db_threshold,
                LORA_FINETUNING_PROCESS_KEY,
            )
        elif previous_count < db_threshold <= new_count:
            should_start_lora = True
            lora_new_count = new_count
            lora_threshold = db_threshold

        await db.commit()
    except IntegrityError:
        await db.rollback()
        try:
            internal_client.remove_object(GOLDEN_SET_BUCKET, object_rel)
        except Exception:
            logger.warning("golden_set orphan cleanup failed for %s (idempotency race)", object_rel)
        ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "golden_set audio_id=%s idempotency race; treating as duplicate duration_ms=%.0f",
            body.audio_id,
            ms,
        )
        return {"status": "ok", "idempotent": True, "idempotency_key": ik, "minio_object_key": minio_key}
    except Exception:
        await db.rollback()
        try:
            internal_client.remove_object(GOLDEN_SET_BUCKET, object_rel)
        except Exception:
            logger.warning("golden_set orphan cleanup failed for %s", object_rel)
        raise

    ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "golden_set audio_id=%s task_id=%s entries_written=1 idempotency_hit=0 minio_key=%s duration_ms=%.0f",
        body.audio_id,
        body.label_studio_task_id,
        minio_key,
        ms,
    )
    if should_start_lora:
        await start_lora_finetuning_camunda(lora_new_count, lora_threshold)
    return {
        "status": "ok",
        "idempotent": False,
        "idempotency_key": ik,
        "minio_object_key": minio_key,
    }


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


# ─── Routes — Golden Set (Story 4.1) ─────────────────────────────────────────


@app.post("/v1/golden-set/entry")
async def post_golden_set_entry(
    request: Request,
    body: GoldenSetEntryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Internal ingest — service API key (not Keycloak). See docs/api-mapping.md §4."""
    verify_golden_set_internal_secret(request)
    return await persist_golden_set_entry(db, body)


@app.get("/v1/golden-set/status", response_model=GoldenSetStatusResponse)
async def get_golden_set_status(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoldenSetStatusResponse:
    """Golden Set counter snapshot — Manager or Admin. Story 4.3."""
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    r = await db.execute(select(GoldenSetCounter).where(GoldenSetCounter.id == 1))
    row = r.scalar_one_or_none()
    if row is None:
        return GoldenSetStatusResponse(
            count=0,
            threshold=GOLDEN_SET_THRESHOLD,
            last_training_at=None,
            next_trigger_at=None,
        )
    last_tr = row.last_training_at.isoformat() if row.last_training_at else None
    return GoldenSetStatusResponse(
        count=int(row.count),
        threshold=int(row.threshold),
        last_training_at=last_tr,
        next_trigger_at=None,
    )


@app.post("/v1/golden-set/frontend-correction")
async def post_golden_set_frontend_correction(
    body: FrontendCorrectionRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Browser-facing Golden Set capture — JWT auth (Transcripteur or Admin). Story 4.2."""
    t0 = time.perf_counter()
    roles = get_roles(payload)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})
    if not {"Transcripteur", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Transcripteur or Admin role required"})

    result = await db.execute(
        select(AudioFile)
        .where(AudioFile.id == body.audio_id)
        .options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if "Admin" not in roles:
        asg = af.assignment
        if not asg or asg.transcripteur_id != sub:
            raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})

    if af.status not in (AudioFileStatus.ASSIGNED, AudioFileStatus.IN_PROGRESS):
        raise HTTPException(
            status_code=409,
            detail={"error": "Audio file status does not allow corrections"},
        )

    ik = None
    if body.client_mutation_id:
        parts = {"audio_id": body.audio_id, "client_mutation_id": body.client_mutation_id}
        ik = golden_set.idempotency_key_from_parts(parts)

    req = GoldenSetEntryRequest(
        audio_id=body.audio_id,
        segment_start=body.segment_start,
        segment_end=body.segment_end,
        original_text=body.original_text,
        corrected_text=body.corrected_text,
        label=body.label,
        source="frontend_correction",
        weight="standard",
        idempotency_key=ik,
    )

    out = await persist_golden_set_entry(db, req)

    ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "frontend_correction audio_id=%s user_sub=%s segment_start=%.2f segment_end=%.2f "
        "entries_written=%d idempotency_hit=%s minio_key=%s duration_ms=%.0f",
        body.audio_id,
        sub,
        body.segment_start,
        body.segment_end,
        0 if out.get("idempotent") else 1,
        "1" if out.get("idempotent") else "0",
        out.get("minio_object_key", "-"),
        ms,
    )

    return out


# ─── Routes — Transcription read (Story 4.2) ─────────────────────────────────


@app.get("/v1/audio-files/{audio_file_id}/transcription")
async def get_audio_transcription(
    audio_file_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return stored segments for an audio file; empty until callback persists rows (Story 4.2 AC7)."""
    roles = get_roles(payload)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})
    if not {"Transcripteur", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Transcripteur or Admin role required"})

    result = await db.execute(
        select(AudioFile)
        .where(AudioFile.id == audio_file_id)
        .options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if "Admin" not in roles:
        asg = af.assignment
        if not asg or asg.transcripteur_id != sub:
            raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})

    return {"segments": []}


@app.post("/v1/editor/ticket")
async def post_editor_ticket(
    body: EditorTicketRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EditorTicketResponse:
    """
    Mint a single-use WSS handshake ticket (Redis TTL 60s). JWT must not be passed on the WebSocket URL;
    Story 5.1 should send only ticket_id (e.g. query `ticket=`) when connecting.
    """
    roles = get_roles(payload)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})
    if not {"Transcripteur", "Expert", "Admin"}.intersection(roles):
        raise HTTPException(
            status_code=403,
            detail={"error": "Transcripteur, Expert, or Admin role required"},
        )

    result = await db.execute(
        select(AudioFile)
        .where(AudioFile.id == body.document_id)
        .options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if "Admin" not in roles:
        if "Expert" in roles:
            proj_r = await db.execute(select(Project).where(Project.id == af.project_id))
            proj = proj_r.scalar_one_or_none()
            if proj is None or proj.status != ProjectStatus.ACTIVE:
                raise HTTPException(status_code=403, detail={"error": "Project is not active"})
        elif "Transcripteur" in roles:
            asg = af.assignment
            if not asg or asg.transcripteur_id != sub:
                raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})
            if af.status not in (AudioFileStatus.ASSIGNED, AudioFileStatus.IN_PROGRESS):
                raise HTTPException(
                    status_code=409,
                    detail={"error": "Audio file status does not allow editor access"},
                )
        else:
            raise HTTPException(
                status_code=403,
                detail={"error": "Transcripteur, Expert, or Admin role required"},
            )

    if _redis_client is None:
        raise HTTPException(status_code=503, detail={"error": "Redis unavailable"})

    ticket_id = editor_ticket.new_ticket_id()
    try:
        await editor_ticket.store_ticket(
            _redis_client,
            ticket_id,
            sub=sub,
            document_id=body.document_id,
            permissions=list(body.permissions),
        )
    except Exception as exc:
        logger.exception("Redis error while storing WSS ticket: %s", exc)
        raise HTTPException(status_code=503, detail={"error": "Redis unavailable"})

    return EditorTicketResponse(ticket_id=ticket_id, ttl=editor_ticket.WSS_TICKET_TTL_SEC)


@app.post("/v1/callback/expert-validation")
async def post_expert_validation_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Label Studio webhook — docs/api-mapping.md §5.
    Configure in Label Studio: Project Settings → Webhooks; use actions such as
    ANNOTATION_UPDATED / ANNOTATION_CREATED when an expert submits or updates an annotation.
    """
    verify_label_studio_webhook_secret(request)
    try:
        raw = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "Invalid JSON"})
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail={"error": "Invalid JSON body"})

    norm = golden_set.normalize_expert_validation_payload(raw)

    action = norm.get("action")
    if action is not None and action not in _GOLDEN_SET_ACTIONS:
        return {
            "status": "ok",
            "entries_written": 0,
            "idempotency_hits": 0,
            "task_id": norm["task_id"],
            "skipped_action": action,
        }

    audio_id = norm["audio_id"]
    if audio_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "audio_id is required (top-level or task.data.audio_id)"},
        )
    if audio_id <= 0:
        raise HTTPException(
            status_code=400,
            detail={"error": "audio_id must be a positive integer"},
        )

    segments = norm["segments"]
    if not segments:
        return {
            "status": "ok",
            "entries_written": 0,
            "idempotency_hits": 0,
            "task_id": norm["task_id"],
        }

    entries_written = 0
    idempotency_hits = 0
    skipped = 0
    for seg in segments:
        parts = {
            "ann": norm["annotation_id"],
            "task": norm["task_id"],
            "s0": seg["segment_start"],
            "s1": seg["segment_end"],
            "t": seg["corrected_text"],
            "label": seg["label"],
        }
        ik = golden_set.idempotency_key_from_parts(parts)
        try:
            req = GoldenSetEntryRequest(
                audio_id=audio_id,
                segment_start=seg["segment_start"],
                segment_end=seg["segment_end"],
                corrected_text=seg["corrected_text"],
                label=seg["label"],
                source="label_studio",
                weight="high",
                original_text=seg.get("original_text"),
                idempotency_key=ik,
                label_studio_task_id=norm["task_id"],
                label_studio_annotation_id=norm["annotation_id"],
            )
        except (ValidationError, ValueError) as exc:
            logger.warning("golden_set skipping invalid segment task_id=%s: %s", norm["task_id"], exc)
            skipped += 1
            continue
        out = await persist_golden_set_entry(
            db,
            req,
            label_studio_project_id_for_verify=norm["label_studio_project_id"],
        )
        if out.get("idempotent"):
            idempotency_hits += 1
        else:
            entries_written += 1

    return {
        "status": "ok",
        "entries_written": entries_written,
        "idempotency_hits": idempotency_hits,
        "task_id": norm["task_id"],
    }


@app.post("/v1/callback/model-ready")
async def post_model_ready_callback(
    request: Request,
    body: ModelReadyCallbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    LoRA registry worker — after MinIO publish + models/latest update (Story 4.4).
    Resets GoldenSetCounter for the next threshold cycle; idempotent per training_run_id.
    """
    verify_model_ready_callback_secret(request)

    stmt = (
        pg_insert(ModelReadyIdempotency)
        .values(training_run_id=body.training_run_id)
        .on_conflict_do_nothing(index_elements=[ModelReadyIdempotency.training_run_id])
        .returning(ModelReadyIdempotency.training_run_id)
    )
    ins = await db.execute(stmt)
    if ins.scalar_one_or_none() is None:
        await db.commit()
        return {"status": "ok", "idempotent": True}

    completed_at = datetime.now(timezone.utc)
    cr = await db.execute(select(GoldenSetCounter).where(GoldenSetCounter.id == 1).with_for_update())
    ctr = cr.scalar_one_or_none()
    if ctr is None:
        ctr = GoldenSetCounter(id=1, count=0, threshold=GOLDEN_SET_THRESHOLD)
        db.add(ctr)
        await db.flush()

    ctr.last_training_at = completed_at
    ctr.count = 0
    await db.commit()

    logger.info(
        "model_ready_callback training_run_id=%s model_version=%s wer_score=%s minio_path=%s",
        body.training_run_id,
        body.model_version,
        body.wer_score,
        body.minio_path,
    )

    return {
        "status": "ok",
        "idempotent": False,
        "last_training_at": completed_at.isoformat().replace("+00:00", "Z"),
    }
