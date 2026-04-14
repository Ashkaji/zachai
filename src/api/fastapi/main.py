"""
ZachAI FastAPI Gateway — Story 4.1–4.4: Golden Set + LoRA pipeline
Extends Story 2.4: Assignment dashboard + FFmpeg semantics fix.
Golden Set: POST /v1/golden-set/entry, frontend-correction, expert webhook; Story 5.2: POST /v1/editor/ticket (Redis WSS handshake); threshold crossing starts `lora-fine-tuning` BPMN (Story 4.3–4.4).
POST /v1/callback/model-ready resets counter after successful registry publish (Story 4.4).
FastAPI never touches audio binary data — upload goes directly browser→MinIO.
"""
import os
import io
import json
import re
import hashlib
import base64
import uuid
import hmac
import math
import logging
import html
import time
import asyncio
import ipaddress
import socket
import zipfile
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import timedelta, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator
from urllib.parse import quote_plus, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload
from sqlalchemy import String, Boolean, Integer, Float, ForeignKey, DateTime, Text, LargeBinary, func, select, delete, Index, case, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.exc import IntegrityError
from lxml import etree

import golden_set
import editor_ticket
import keycloak_admin

import redis.asyncio as redis_asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Env var validation ───────────────────────────────────────────────────────

REQUIRED_ENV_VARS = [
    "KEYCLOAK_ISSUER",
    "KEYCLOAK_ADMIN_CLIENT_ID",
    "KEYCLOAK_ADMIN_CLIENT_SECRET",
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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


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
_SNAPSHOT_CALLBACK_SECRET: str = (os.environ.get("SNAPSHOT_CALLBACK_SECRET") or "").strip()
_WHISPER_OPEN_API_KEY: str = (os.environ.get("WHISPER_OPEN_API_KEY") or "").strip()
EXPORT_WORKER_URL: str = (os.environ.get("EXPORT_WORKER_URL") or "http://export-worker:8780").rstrip("/")
OPENVINO_WORKER_URL: str = (os.environ.get("OPENVINO_WORKER_URL") or "http://openvino-worker:8770").rstrip("/")
_CHANGEME_PREFIXES = ("changeme",)
if _LABEL_STUDIO_WEBHOOK_SECRET and _LABEL_STUDIO_WEBHOOK_SECRET.startswith(_CHANGEME_PREFIXES):
    logger.warning("LABEL_STUDIO_WEBHOOK_SECRET uses a default 'changeme' value — override in production")
if _GOLDEN_SET_INTERNAL_SECRET and _GOLDEN_SET_INTERNAL_SECRET.startswith(_CHANGEME_PREFIXES):
    logger.warning("GOLDEN_SET_INTERNAL_SECRET uses a default 'changeme' value — override in production")
if _MODEL_READY_CALLBACK_SECRET and _MODEL_READY_CALLBACK_SECRET.startswith(_CHANGEME_PREFIXES):
    logger.warning("MODEL_READY_CALLBACK_SECRET uses a default 'changeme' value — override in production")
if _SNAPSHOT_CALLBACK_SECRET and _SNAPSHOT_CALLBACK_SECRET.startswith(_CHANGEME_PREFIXES):
    logger.warning("SNAPSHOT_CALLBACK_SECRET uses a default 'changeme' value — override in production")
if _WHISPER_OPEN_API_KEY and _WHISPER_OPEN_API_KEY.startswith(_CHANGEME_PREFIXES):
    logger.warning("WHISPER_OPEN_API_KEY uses a default 'changeme' value — override in production")

_raw_whisper_fetch_timeout = os.environ.get("WHISPER_OPEN_API_FETCH_TIMEOUT", "20")
try:
    WHISPER_OPEN_API_FETCH_TIMEOUT: float = max(1.0, float(_raw_whisper_fetch_timeout))
except (TypeError, ValueError):
    logger.warning("WHISPER_OPEN_API_FETCH_TIMEOUT=%r invalid; using 20.0", _raw_whisper_fetch_timeout)
    WHISPER_OPEN_API_FETCH_TIMEOUT = 20.0
_raw_whisper_upstream_timeout = os.environ.get("WHISPER_OPEN_API_UPSTREAM_TIMEOUT", "120")
try:
    WHISPER_OPEN_API_UPSTREAM_TIMEOUT: float = max(1.0, float(_raw_whisper_upstream_timeout))
except (TypeError, ValueError):
    logger.warning("WHISPER_OPEN_API_UPSTREAM_TIMEOUT=%r invalid; using 120.0", _raw_whisper_upstream_timeout)
    WHISPER_OPEN_API_UPSTREAM_TIMEOUT = 120.0
_raw_whisper_max_bytes = os.environ.get("WHISPER_OPEN_API_MAX_AUDIO_BYTES", str(100 * 1024 * 1024))
try:
    WHISPER_OPEN_API_MAX_AUDIO_BYTES: int = max(1024, int(_raw_whisper_max_bytes))
except (TypeError, ValueError):
    logger.warning("WHISPER_OPEN_API_MAX_AUDIO_BYTES=%r invalid; using 104857600", _raw_whisper_max_bytes)
    WHISPER_OPEN_API_MAX_AUDIO_BYTES = 100 * 1024 * 1024
_raw_whisper_max_duration = os.environ.get("WHISPER_OPEN_API_MAX_DURATION_S", "14400")
try:
    WHISPER_OPEN_API_MAX_DURATION_S: float = max(1.0, float(_raw_whisper_max_duration))
except (TypeError, ValueError):
    logger.warning("WHISPER_OPEN_API_MAX_DURATION_S=%r invalid; using 14400", _raw_whisper_max_duration)
    WHISPER_OPEN_API_MAX_DURATION_S = 14400.0

_GOLDEN_SET_ACTIONS = frozenset({"ANNOTATION_CREATED", "ANNOTATION_UPDATED", "ANNOTATION_SUBMITTED"})

PLATFORM_SALT: str = os.environ.get("PLATFORM_SALT", "zachai-default-salt")

# FFmpeg worker HTTP client — created in lifespan (real AsyncClient; tests avoid import-time mock issues)
_ffmpeg_client: httpx.AsyncClient | None = None
# Export worker HTTP client — Story 5.4 snapshot pipeline
_export_worker_client: httpx.AsyncClient | None = None

# Redis — WSS editor tickets (Story 5.2); optional at runtime if ping fails (mint → 503)
_redis_client: redis_asyncio.Redis | None = None

# LanguageTool grammar proxy (Story 5.5)
_LANGUAGETOOL_BASE_URL: str = (
    (os.environ.get("LANGUAGETOOL_URL") or "http://languagetool:8010").strip().rstrip("/")
)
_raw_grammar_ttl = os.environ.get("GRAMMAR_CACHE_TTL_SEC", "300")
try:
    GRAMMAR_CACHE_TTL_SEC: int = max(0, int(_raw_grammar_ttl))
except (TypeError, ValueError):
    logger.warning(
        "GRAMMAR_CACHE_TTL_SEC=%r invalid; using 300",
        _raw_grammar_ttl,
    )
    GRAMMAR_CACHE_TTL_SEC = 300
_raw_grammar_max = os.environ.get("GRAMMAR_MAX_TEXT_LEN", "65536")
try:
    GRAMMAR_MAX_TEXT_LEN: int = max(256, int(_raw_grammar_max))
except (TypeError, ValueError):
    logger.warning("GRAMMAR_MAX_TEXT_LEN=%r invalid; using 65536", _raw_grammar_max)
    GRAMMAR_MAX_TEXT_LEN = 65536
_raw_grammar_timeout = os.environ.get("GRAMMAR_HTTP_TIMEOUT", "20")
try:
    GRAMMAR_HTTP_TIMEOUT: float = max(1.0, float(_raw_grammar_timeout))
except (TypeError, ValueError):
    logger.warning("GRAMMAR_HTTP_TIMEOUT=%r invalid; using 20.0", _raw_grammar_timeout)
    GRAMMAR_HTTP_TIMEOUT = 20.0
LT_GRAMMAR_CACHE_PREFIX = "lt:grammar:"
_raw_grammar_rate_limit = os.environ.get("GRAMMAR_RATE_LIMIT_PER_MIN", "120")
try:
    GRAMMAR_RATE_LIMIT_PER_MIN: int = max(0, int(_raw_grammar_rate_limit))
except (TypeError, ValueError):
    logger.warning("GRAMMAR_RATE_LIMIT_PER_MIN=%r invalid; using 120", _raw_grammar_rate_limit)
    GRAMMAR_RATE_LIMIT_PER_MIN = 120

# Bible verse HTTP cache (Story 13.2) — optional Redis; PostgreSQL remains source of truth
_raw_bible_cache_enabled = (os.environ.get("BIBLE_VERSE_CACHE_ENABLED") or "false").strip().lower()
BIBLE_VERSE_CACHE_ENABLED: bool = _raw_bible_cache_enabled in ("1", "true", "yes", "on")
_raw_bible_verse_ttl = os.environ.get("BIBLE_VERSE_CACHE_TTL_SEC", "600")
try:
    BIBLE_VERSE_CACHE_TTL_SEC: int = max(0, int(_raw_bible_verse_ttl))
except (TypeError, ValueError):
    logger.warning(
        "BIBLE_VERSE_CACHE_TTL_SEC=%r invalid; using 600",
        _raw_bible_verse_ttl,
    )
    BIBLE_VERSE_CACHE_TTL_SEC = 600
BIBLE_VERSE_GEN_PREFIX = "bible:verse:gen:"
BIBLE_VERSE_CACHE_KEY_PREFIX = "bible:verse:v1:"


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


class SnapshotArtifact(Base):
    """Snapshot export metadata for timeline/restore workflows (Story 5.4)."""

    __tablename__ = "snapshot_artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audio_files.id", ondelete="CASCADE"), nullable=False
    )
    json_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    docx_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    yjs_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    json_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    docx_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="hocuspocus-idle-callback")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_snapshot_artifacts_document_created", "document_id", "created_at"),)


class UserConsent(Base):
    """RGPD consent and account deletion tracking (Story 12.1)."""

    __tablename__ = "user_consents"
    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)  # sub from Keycloak
    ml_usage_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    biometric_data_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deletion_pending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuditLog(Base):
    """Chronological log of major actions within a project (Story 10.4)."""

    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)  # sub from JWT
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(LargeBinary, nullable=False)  # Store as JSON binary for flexibility
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_audit_logs_project_id", "project_id"),)


class ManagerMembership(Base):
    """Manager/Member mapping (Story 16.2) — one user belongs to exactly one manager."""

    __tablename__ = "manager_memberships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("member_id", name="uq_manager_membership_member"),
    )


class ModelReadyIdempotency(Base):
    """One row per successful model-ready callback (Story 4.4) — dedupes worker retries."""

    __tablename__ = "model_ready_idempotency"
    training_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BibleVerse(Base):
    """Local Bible engine storage (Story 11.5)."""

    __tablename__ = "bible_verses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    translation: Mapped[str] = mapped_column(String(32), nullable=False)  # LSG, KJV, etc.
    book: Mapped[str] = mapped_column(String(255), nullable=False)
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    verse: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("translation", "book", "chapter", "verse", name="uq_bible_lookup"),
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
    global _jwks_cache, _ffmpeg_client, _redis_client, _export_worker_client
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

            # Brownfield schema compatibility (Story 2.3):
            # `create_all()` doesn't modify existing tables, but the app expects validation_* columns.
            # Use IF NOT EXISTS so repeated startups are safe.
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS validation_error VARCHAR(1024)"
                    )
                )
                await conn.execute(
                    text(
                        "ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS validation_attempted_at TIMESTAMPTZ"
                    )
                )

                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_audio_files_project_status ON audio_files (project_id, status)"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_files_project_minio_path ON audio_files (project_id, minio_path)"
                    )
                )

                # Story 10.4: Audit logs
                await conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS audit_logs ("
                        "id SERIAL PRIMARY KEY, "
                        "project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                        "user_id VARCHAR(255) NOT NULL, "
                        "action VARCHAR(64) NOT NULL, "
                        "details BYTEA NOT NULL, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                        ")"
                    )
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_audit_logs_project_id ON audit_logs (project_id)")
                )

                # Story 12.1: User consents
                await conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS user_consents ("
                        "user_id VARCHAR(255) PRIMARY KEY, "
                        "ml_usage_approved BOOLEAN NOT NULL DEFAULT FALSE, "
                        "biometric_data_approved BOOLEAN NOT NULL DEFAULT FALSE, "
                        "deletion_pending_at TIMESTAMPTZ, "
                        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                        ")"
                    )
                )

                # Story 16.2: Manager memberships
                await conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS manager_memberships ("
                        "id SERIAL PRIMARY KEY, "
                        "manager_id VARCHAR(255) NOT NULL, "
                        "member_id VARCHAR(255) NOT NULL UNIQUE, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                        ")"
                    )
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_manager_memberships_manager_id ON manager_memberships (manager_id)")
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_manager_memberships_member_id ON manager_memberships (member_id)")
                )
            except Exception as ddl_exc:
                logger.warning(
                    "Brownfield audio_files/audit_logs DDL skipped/failed (will likely break endpoints): %s",
                    ddl_exc,
                )
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

    # Bible verse cache (Story 13.2) — observability for operators
    if BIBLE_VERSE_CACHE_ENABLED and BIBLE_VERSE_CACHE_TTL_SEC > 0:
        if _redis_client is not None:
            logger.info(
                "Bible verse Redis cache enabled (TTL %ss)",
                BIBLE_VERSE_CACHE_TTL_SEC,
            )
        else:
            logger.warning(
                "BIBLE_VERSE_CACHE_ENABLED but Redis unavailable — GET /v1/bible/verses will use PostgreSQL only",
            )
    elif BIBLE_VERSE_CACHE_ENABLED and BIBLE_VERSE_CACHE_TTL_SEC <= 0:
        logger.warning(
            "BIBLE_VERSE_CACHE_ENABLED but BIBLE_VERSE_CACHE_TTL_SEC<=0 — Bible verse Redis cache disabled",
        )

    # Export worker — Story 5.4 (snapshot conversion/upload pipeline).
    if EXPORT_WORKER_URL:
        _export_worker_client = httpx.AsyncClient(base_url=EXPORT_WORKER_URL, timeout=30.0)
        try:
            hr = await _export_worker_client.get("/health", timeout=5.0)
            if hr.status_code != 200:
                logger.warning("Export worker /health returned HTTP %s", hr.status_code)
        except Exception as exc:
            logger.warning("Export worker unreachable at startup — snapshot callback may fail: %s", exc)
    else:
        logger.warning("EXPORT_WORKER_URL empty — snapshot callback endpoint will return 503")
        _export_worker_client = None

    yield

    if _ffmpeg_client is not None:
        await _ffmpeg_client.aclose()
        _ffmpeg_client = None
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _export_worker_client is not None:
        await _export_worker_client.aclose()
        _export_worker_client = None
    await engine.dispose()
    await camunda_client.aclose()


# Story 8.1 Traceability
request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request-id")

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

# Ensure root logger has the filter and proper format
root_logger = logging.getLogger()
if root_logger.handlers:
    for handler in root_logger.handlers:
        handler.addFilter(RequestIdFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"))

# OpenAPI /docs sidebar: group routes by domain (single tag per operation).
OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "Health", "description": "Orchestration liveness."},
    {"name": "Presigned uploads", "description": "Browser→MinIO presigned PUT/GET; binaries never pass through FastAPI."},
    {"name": "Natures", "description": "Project nature templates and label schemas."},
    {"name": "Projects", "description": "Projects, lifecycle, audit trail, assignment, dashboard status."},
    {"name": "Project audio", "description": "Presign upload, register, FFmpeg normalization for project audio."},
    {"name": "Tasks", "description": "Transcripteur and Expert work queues."},
    {"name": "Profile & GDPR", "description": "Current user profile, consents, export, deletion workflow."},
    {"name": "Admin", "description": "Privileged maintenance (e.g. purge user)."},
    {"name": "Snapshots & history", "description": "Yjs snapshot listing, fetch, restore, Ghost Mode data."},
    {"name": "Golden Set", "description": "Training pairs, Label Studio ingest, LoRA threshold counter."},
    {"name": "Transcription workflow", "description": "Submit, validate, read transcription segments."},
    {"name": "Export", "description": "Validated transcript/subtitle downloads."},
    {"name": "Open APIs", "description": "Whisper ASR and citation detection (API-key auth, not Keycloak)."},
    {"name": "Media", "description": "Presigned playback URL for normalized audio."},
    {"name": "Editor & collaboration", "description": "WSS ticket, grammar proxy, Hocuspocus snapshot callback."},
    {"name": "Webhooks & callbacks", "description": "Label Studio, LoRA model-ready, internal secrets."},
    {"name": "Bible", "description": "Local sovereign verse retrieval and bulk ingest."},
    {"name": "IAM", "description": "Identity and Access Management perimeter mapping (Story 16.2)."},
]

app = FastAPI(
    title="ZachAI Gateway",
    description="Lean API gateway: presigned URLs, JWT, Nature CRUD, Project CRUD, audio upload, Golden Set, Camunda 7",
    version="2.11.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_var.reset(token)

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
            options={
                "verify_aud": False,  # realm-level roles — no audience claim to verify
                # OIDC id_tokens include at_hash; python-jose would require the access_token
                # argument to verify it, but our clients send only one Bearer. Access tokens
                # do not carry at_hash, so skipping is safe for API auth.
                "verify_at_hash": False,
            },
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"error": "Token expired"})
    except JWTError:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})


def get_roles(payload: dict) -> list[str]:
    """
    Extract Keycloak roles from JWT: realm roles (`realm_access.roles`) plus any client roles
    under `resource_access.<client>.roles`. Both appear depending on client-scope mappers;
    merging avoids 403 when the UI shows realm roles but only client claims are in the token.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add_list(role_list: object) -> None:
        if not isinstance(role_list, list):
            return
        for r in role_list:
            name = r if isinstance(r, str) else str(r)
            if name not in seen:
                seen.add(name)
                out.append(name)

    ra = payload.get("realm_access")
    if isinstance(ra, dict):
        add_list(ra.get("roles"))

    rac = payload.get("resource_access")
    if isinstance(rac, dict):
        for _client_id, caccess in rac.items():
            if isinstance(caccess, dict):
                add_list(caccess.get("roles"))

    return out


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> dict:
    """FastAPI dependency: extract and verify Bearer JWT, return decoded payload. 
    Blocks access if deletion is pending (Story 12.1 AC 5)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})
    payload = decode_token(credentials.credentials)

    # sub fallback logic
    if not payload.get("sub"):
        for alt in ("preferred_username", "username", "email", "upn"):
            v = payload.get(alt)
            if isinstance(v, str) and v.strip():
                payload["sub"] = v
                break
    
    sub = payload.get("sub")
    if sub:
        # Check deletion_pending_at except for GET /v1/me/profile and cancel request
        # This prevents any authenticated action (except Profile GET) if deletion is pending.
        is_profile_get = request.method == "GET" and request.url.path == "/v1/me/profile"
        is_delete_cancel = request.method == "POST" and request.url.path == "/v1/me/delete-cancel"
        
        if not is_profile_get and not is_delete_cancel:
            result = await db.execute(select(UserConsent).where(UserConsent.user_id == sub))
            consent = result.scalar_one_or_none()
            if consent and consent.deletion_pending_at:
                raise HTTPException(
                    status_code=403, 
                    detail={"error": "Account deletion pending. All write operations and data access are blocked."}
                )

    return payload


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


class ExpertTaskResponse(BaseModel):
    audio_id: int
    project_id: int
    project_name: str
    filename: str
    status: str
    assigned_at: str | None
    expert_id: str | None
    source: str
    priority: str | None = None


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


class GrammarProxyRequest(BaseModel):
    """POST /v1/proxy/grammar — Story 5.5 (LanguageTool via FastAPI)."""

    text: str = Field(..., min_length=1, max_length=262144)
    language: str = Field(..., min_length=2, max_length=32)

    @field_validator("text")
    @classmethod
    def _text_non_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must contain non-whitespace characters")
        return v

    @field_validator("language")
    @classmethod
    def _language_code(cls, v: str) -> str:
        s = v.strip().replace("_", "-")
        low = s.lower()
        if low == "auto":
            return "auto"
        if not re.fullmatch(r"[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})?", s):
            raise ValueError("invalid language code for LanguageTool")
        return low


class WhisperOpenApiRequest(BaseModel):
    """POST /v1/whisper/transcribe — external API key contract (Story 7.2)."""

    audio_url: str = Field(..., min_length=1, max_length=2048)
    language: str | None = Field(None, min_length=1, max_length=32)

    @field_validator("audio_url")
    @classmethod
    def _audio_url_not_blank(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("audio_url cannot be empty")
        return s


class CitationDetectRequest(BaseModel):
    """POST /v1/nlp/detect-citations — external citation detection contract (Story 7.3)."""

    text: str = Field(..., min_length=1, max_length=262144)

    @field_validator("text")
    @classmethod
    def _text_non_whitespace(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("text must contain non-whitespace characters")
        return v


class ManagerMembershipCreate(BaseModel):
    """POST /v1/iam/memberships — Story 16.2."""

    manager_id: str = Field(..., min_length=1, max_length=255)
    member_id: str = Field(..., min_length=1, max_length=255)


class UserCreate(BaseModel):
    """POST /v1/iam/users — Story 16.3."""

    username: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    first_name: str = Field(..., alias="firstName", min_length=1, max_length=255)
    last_name: str = Field(..., alias="lastName", min_length=1, max_length=255)
    enabled: bool = True
    role: str = Field(..., pattern="^(Admin|Manager|Transcripteur|Expert)$")

    model_config = {
        "populate_by_name": True
    }


class UserUpdate(BaseModel):
    """PATCH /v1/iam/users/{user_id} — Story 16.3."""

    enabled: bool


class EditorSnapshotCallbackRequest(BaseModel):
    """POST /v1/editor/callback/snapshot — Hocuspocus idle snapshot callback (Story 5.4)."""

    document_id: int = Field(..., gt=0)
    yjs_state_binary: str = Field(..., min_length=1, max_length=8_000_000)

    @field_validator("yjs_state_binary")
    @classmethod
    def _validate_snapshot_base64(cls, v: str) -> str:
        try:
            base64.b64decode(v.encode("ascii"), validate=True)
        except Exception as exc:
            raise ValueError("yjs_state_binary must be valid base64") from exc
        return v


class TranscriptionValidationRequest(BaseModel):
    """POST /v1/transcriptions/{audio_id}/validate — Story 6.2."""

    approved: bool
    comment: str | None = Field(
        None, max_length=5000, description="Required when approved=false; optional for approval."
    )


class DocumentRestoreRequest(BaseModel):
    """POST /v1/editor/restore/{audio_id} — Story 12.3."""

    snapshot_id: str


class BibleVerseIn(BaseModel):
    translation: str = Field(..., min_length=1, max_length=32)
    book: str = Field(..., min_length=1, max_length=255)
    chapter: int = Field(..., gt=0)
    verse: int = Field(..., gt=0)
    text: str = Field(..., min_length=1)


class BibleIngestRequest(BaseModel):
    verses: list[BibleVerseIn] = Field(..., min_length=1, max_length=1000)


class BibleVerseOut(BaseModel):
    verse: int
    text: str


class BibleRetrievalResponse(BaseModel):
    reference: str
    translation: str
    verses: list[BibleVerseOut]


class UserConsentStatus(BaseModel):
    ml_usage: bool
    biometric_data: bool
    deletion_pending: bool
    updated_at: str


class UserProfileResponse(BaseModel):
    sub: str
    name: str | None
    email: str | None
    roles: list[str]
    consents: UserConsentStatus


class UserConsentUpdate(BaseModel):
    ml_usage: bool
    biometric_data: bool


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _grammar_cache_key(text: str, language: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{LT_GRAMMAR_CACHE_PREFIX}{digest}:{language}"


def _grammar_rate_limit_key(sub: str) -> str:
    return f"{LT_GRAMMAR_CACHE_PREFIX}rl:{sub}"


def _basic_regex_matches(text: str) -> list[dict[str, Any]]:
    """Minimal local fallback when LanguageTool is overloaded (PRD §4.8)."""
    out: list[dict[str, Any]] = []
    for m in re.finditer(r" {2,}", text):
        out.append(
            {
                "offset": m.start(),
                "length": m.end() - m.start(),
                "message": "Multiple consecutive spaces",
                "shortMessage": "",
                "ruleId": "ZACHAI_LOCAL_REGEX",
                "category": "TYPOGRAPHY",
                "replacements": [" "],
                "issueType": "grammar",
            }
        )
    return out


def _grammar_category_id(match: dict[str, Any], rule: dict[str, Any]) -> str:
    rc = rule.get("category")
    if isinstance(rc, dict) and rc.get("id") is not None:
        return str(rc["id"])
    if isinstance(rc, str) and rc.strip():
        return rc.strip()
    cat = match.get("category")
    if isinstance(cat, dict) and cat.get("id") is not None:
        return str(cat["id"])
    if isinstance(cat, str) and cat.strip():
        return cat.strip()
    return ""


def _normalize_lt_matches(raw: list[Any], text: str) -> list[dict[str, Any]]:
    text_len = len(text)
    out: list[dict[str, Any]] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        repl: list[str] = []
        for r in m.get("replacements") or []:
            if isinstance(r, dict) and r.get("value") is not None:
                repl.append(str(r["value"]))
        rule = m.get("rule") if isinstance(m.get("rule"), dict) else {}
        rule_id = str(rule.get("id") or "")
        cat_id = _grammar_category_id(m, rule)
        issue_raw = str(rule.get("issueType") or "").lower()
        issue = "spelling" if issue_raw == "misspelling" else "grammar"
        try:
            off = int(m.get("offset", 0))
            ln = int(m.get("length", 0))
        except (TypeError, ValueError):
            continue
        if off < 0 or off > text_len:
            continue
        if off + ln > text_len:
            ln = text_len - off
        if ln <= 0:
            continue
        out.append(
            {
                "offset": off,
                "length": ln,
                "message": str(m.get("message") or ""),
                "shortMessage": str(m.get("shortMessage") or ""),
                "ruleId": rule_id,
                "category": cat_id,
                "replacements": repl,
                "issueType": issue,
            }
        )
    return out


def _grammar_cached_payload_valid(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    matches = data.get("matches")
    degraded = data.get("degraded")
    if not isinstance(matches, list) or not isinstance(degraded, bool):
        return False
    return True


def _is_internal_languagetool_url(base_url: str) -> bool:
    try:
        parsed = urlparse(base_url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in {"languagetool", "localhost", "127.0.0.1", "::1"}:
        return True
    # Docker/service names are typically single-label hosts (no dot).
    if "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _parse_max_speaker_labels(raw: str | None) -> int:
    if raw is None or not str(raw).strip():
        return 10
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid MAX_SPEAKER_LABELS={raw!r}; expected integer >= 1"
        ) from exc
    if value < 1:
        raise RuntimeError("MAX_SPEAKER_LABELS must be >= 1")
    return value


MAX_SPEAKER_LABELS = _parse_max_speaker_labels(os.environ.get("MAX_SPEAKER_LABELS", "10"))
SPEAKER_COLORS = [
    "#4285e4", "#e54242", "#42e567", "#e5a742", "#a742e5",
    "#42e5d1", "#e542a7", "#7be542", "#4242e5", "#e5e542",
]


def generate_label_studio_xml(labels: list) -> str:
    """Generate Label Studio labeling interface XML from a nature's label set.

    Speech labels appear first; non-speech (Pause, Bruit, Musique) follow;
    generic SPEAKER_XX labels are appended for ML pre-annotation (the expert
    reassigns them to the real nature labels).

    ``<TextArea perRegion="true">`` so each audio region gets its own transcript.
    This XML is consumed by Camunda 7 in Story 2.2 to provision Label Studio projects.
    """
    speech = [lb for lb in labels if lb.is_speech]
    non_speech = [lb for lb in labels if not lb.is_speech]

    label_tags = "\n".join(
        f'    <Label value="{html.escape(lb.label_name)}" background="{html.escape(lb.label_color)}"/>'
        for lb in speech + non_speech
    )

    speaker_tags = "\n".join(
        f'    <Label value="SPEAKER_{i:02d}" background="{SPEAKER_COLORS[i % len(SPEAKER_COLORS)]}"/>'
        for i in range(MAX_SPEAKER_LABELS)
    )

    return (
        "<View>\n"
        '  <AudioPlus name="audio" value="$audio"/>\n'
        '  <Labels name="label" toName="audio">\n'
        f"{label_tags}\n"
        f"{speaker_tags}\n"
        "  </Labels>\n"
        '  <TextArea name="transcription" toName="audio" perRegion="true" '
        'editable="true" rows="3" displayMode="region-list" '
        'placeholder="Transcription..."/>\n'
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


def _sanitize_export_stem(name: str | None, fallback: str) -> str:
    base = (name or "").strip()
    if "." in base:
        base = base.rsplit(".", 1)[0]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return base or fallback


def _format_srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000.0))
    hours, rem = divmod(millis, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _build_srt_content(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    prev_start = -1.0
    for idx, seg in enumerate(segments, start=1):
        start = float(seg["start"])
        end = float(seg["end"])
        text_val = str(seg.get("text") or "").strip()
        if start < 0:
            raise ValueError("segment start must be >= 0")
        if end <= start:
            raise ValueError("segment duration must be positive")
        if start < prev_start:
            raise ValueError("segment timestamps must be non-descending")
        prev_start = start
        if not text_val:
            text_val = "[inaudible]"
        lines.append(str(idx))
        lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        lines.append(text_val)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def _resolve_audio_for_export(
    db: AsyncSession,
    audio_id: int,
    payload: dict,
    roles: list[str],
) -> AudioFile:
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})

    if not {"Transcripteur", "Manager", "Admin"}.intersection(roles):
        raise HTTPException(
            status_code=403,
            detail={"error": "Transcripteur, Manager, or Admin role required"},
        )

    result = await db.execute(
        select(AudioFile).where(AudioFile.id == audio_id).options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    pr = await db.execute(select(Project).where(Project.id == af.project_id))
    project = pr.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found for audio file"})

    if "Admin" in roles:
        return af
    if "Manager" in roles:
        _require_project_owner_or_admin(project, payload, roles)
        return af
    if "Transcripteur" in roles:
        asg = af.assignment
        if not asg or asg.transcripteur_id != sub:
            raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})
        return af
    raise HTTPException(
        status_code=403,
        detail={"error": "Transcripteur, Manager, or Admin role required"},
    )


async def _load_latest_snapshot_payload(db: AsyncSession, audio_id: int) -> tuple[SnapshotArtifact, dict[str, Any]]:
    row = await db.execute(
        select(SnapshotArtifact)
        .where(SnapshotArtifact.document_id == audio_id)
        .order_by(SnapshotArtifact.created_at.desc(), SnapshotArtifact.id.desc())
        .limit(1)
    )
    snap = row.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail={"error": "No snapshot artifact available for export"})

    bucket, obj = _parse_bucket_and_object(snap.json_object_key)
    try:
        resp = internal_client.get_object(bucket, obj)
        data = resp.read()
        resp.close()
        resp.release_conn()
    except S3Error:
        raise HTTPException(status_code=503, detail={"error": "MinIO unavailable"})
    except Exception:
        raise HTTPException(status_code=502, detail={"error": "Snapshot JSON fetch failed"})

    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=502, detail={"error": "Snapshot JSON is invalid"})
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail={"error": "Snapshot JSON payload shape invalid"})
    return snap, parsed


async def _load_latest_snapshot_artifact(db: AsyncSession, audio_id: int) -> SnapshotArtifact:
    row = await db.execute(
        select(SnapshotArtifact)
        .where(SnapshotArtifact.document_id == audio_id)
        .order_by(SnapshotArtifact.created_at.desc(), SnapshotArtifact.id.desc())
        .limit(1)
    )
    snap = row.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail={"error": "No snapshot artifact available for export"})
    return snap


def _extract_segments_from_snapshot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("segments")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for seg in raw:
        if not isinstance(seg, dict):
            continue
        start_val = seg.get("start", seg.get("segment_start"))
        end_val = seg.get("end", seg.get("segment_end"))
        text_val = seg.get("text", seg.get("corrected_text", seg.get("original_text", "")))
        if start_val is None or end_val is None:
            continue
        try:
            start_num = float(start_val)
            end_num = float(end_val)
        except (TypeError, ValueError):
            raise ValueError("segment timestamps must be numeric")
        out.append({"start": start_num, "end": end_num, "text": str(text_val or "").strip()})
    return out


def _extract_text_from_snapshot(payload: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    for key in ("text", "transcript", "final_text", "content"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    if segments:
        return "\n".join(str(seg.get("text") or "").strip() for seg in segments if str(seg.get("text") or "").strip())
    return ""


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


def verify_snapshot_callback_secret(request: Request) -> None:
    _verify_shared_secret(
        request,
        expected_secret=_SNAPSHOT_CALLBACK_SECRET,
        header_name="X-ZachAI-Snapshot-Secret",
        unconfigured_msg="Snapshot callback is not configured",
    )


def verify_whisper_open_api_key(request: Request) -> None:
    _verify_shared_secret(
        request,
        expected_secret=_WHISPER_OPEN_API_KEY,
        header_name="X-ZachAI-Whisper-Api-Key",
        unconfigured_msg="Whisper open API is not configured",
    )


def _validate_whisper_source_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=422, detail={"error": "audio_url is invalid"})
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail={"error": "audio_url scheme must be http or https"})
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=422, detail={"error": "audio_url host is required"})
    blocked_hosts = {"localhost", "127.0.0.1", "::1", "metadata.google.internal", "metadata"}
    if host in blocked_hosts:
        raise HTTPException(status_code=422, detail={"error": "audio_url host is not allowed"})
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise HTTPException(status_code=422, detail={"error": "audio_url target IP is not allowed"})
    except ValueError:
        try:
            addrinfo = socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)
        except Exception:
            raise HTTPException(status_code=422, detail={"error": "audio_url host resolution failed"})
        for info in addrinfo:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise HTTPException(status_code=422, detail={"error": "audio_url resolved to disallowed network"})
    return url


async def _fetch_whisper_source_audio(audio_url: str) -> tuple[bytes, str]:
    safe_url = _validate_whisper_source_url(audio_url)
    try:
        async with httpx.AsyncClient(timeout=WHISPER_OPEN_API_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(safe_url)
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail={"error": "Audio source fetch timeout"})
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail={"error": "Audio source unavailable"})

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail={"error": "Audio source upstream error"})

    content_length = resp.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > WHISPER_OPEN_API_MAX_AUDIO_BYTES:
                raise HTTPException(status_code=422, detail={"error": "audio_url content too large"})
        except ValueError:
            pass

    payload = resp.content
    if not payload:
        raise HTTPException(status_code=422, detail={"error": "audio_url returned empty content"})
    if len(payload) > WHISPER_OPEN_API_MAX_AUDIO_BYTES:
        raise HTTPException(status_code=422, detail={"error": "audio_url content too large"})

    content_type = (resp.headers.get("content-type") or "application/octet-stream").split(";")[0].strip().lower()
    allowed = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave", "application/octet-stream"}
    if content_type not in allowed:
        raise HTTPException(status_code=422, detail={"error": "audio_url content type must be wav"})
    return payload, content_type


def _stage_whisper_audio_to_minio(audio_bytes: bytes, content_type: str) -> tuple[str, str]:
    bucket = "projects"
    object_name = f"external-api/{uuid.uuid4().hex}.wav"
    try:
        internal_client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=io.BytesIO(audio_bytes),
            length=len(audio_bytes),
            content_type=content_type or "audio/wav",
        )
    except Exception:
        raise HTTPException(status_code=503, detail={"error": "MinIO unavailable"})
    return bucket, object_name


async def _call_openvino_transcribe(input_bucket: str, input_key: str) -> dict[str, Any]:
    url = f"{OPENVINO_WORKER_URL}/transcribe"
    try:
        async with httpx.AsyncClient(timeout=WHISPER_OPEN_API_UPSTREAM_TIMEOUT) as client:
            resp = await client.post(url, json={"input_bucket": input_bucket, "input_key": input_key})
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail={"error": "Transcription upstream timeout"})
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail={"error": "Transcription upstream unavailable"})

    if resp.status_code == 400:
        raise HTTPException(status_code=422, detail={"error": "Invalid audio payload for transcription"})
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail={"error": "Transcription upstream error"})
    try:
        data = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail={"error": "Invalid transcription upstream response"})
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail={"error": "Invalid transcription upstream response"})
    return data


def _normalize_openvino_segments(raw_segments: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_segments, list):
        raise HTTPException(status_code=502, detail={"error": "Invalid transcription segments payload"})
    normalized: list[dict[str, Any]] = []
    for seg in raw_segments:
        if not isinstance(seg, dict):
            continue
        try:
            start = float(seg.get("start"))
            end = float(seg.get("end"))
            conf = float(seg.get("confidence")) if seg.get("confidence") is not None else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=502, detail={"error": "Invalid transcription segment shape"})
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            raise HTTPException(status_code=502, detail={"error": "Invalid transcription segment timing"})
        row: dict[str, Any] = {"start": start, "end": end, "text": str(seg.get("text") or "").strip()}
        if conf is not None and math.isfinite(conf):
            row["confidence"] = max(0.0, min(1.0, conf))
        normalized.append(row)
    return normalized


_BIBLE_BOOK_ALIASES: dict[str, str] = {
    # English
    "genesis": "Genesis",
    "gen": "Genesis",
    "exodus": "Exodus",
    "exo": "Exodus",
    "leviticus": "Leviticus",
    "lev": "Leviticus",
    "numbers": "Numbers",
    "num": "Numbers",
    "deuteronomy": "Deuteronomy",
    "deut": "Deuteronomy",
    "joshua": "Joshua",
    "josh": "Joshua",
    "judges": "Judges",
    "judg": "Judges",
    "ruth": "Ruth",
    "1 samuel": "1 Samuel",
    "1 sam": "1 Samuel",
    "2 samuel": "2 Samuel",
    "2 sam": "2 Samuel",
    "1 kings": "1 Kings",
    "1 kgs": "1 Kings",
    "2 kings": "2 Kings",
    "2 kgs": "2 Kings",
    "1 chronicles": "1 Chronicles",
    "1 chr": "1 Chronicles",
    "2 chronicles": "2 Chronicles",
    "2 chr": "2 Chronicles",
    "ezra": "Ezra",
    "nehemiah": "Nehemiah",
    "neh": "Nehemiah",
    "esther": "Esther",
    "job": "Job",
    "psalm": "Psalm",
    "psalms": "Psalm",
    "ps": "Psalm",
    "proverbs": "Proverbs",
    "prov": "Proverbs",
    "ecclesiastes": "Ecclesiastes",
    "eccl": "Ecclesiastes",
    "song of solomon": "Song of Solomon",
    "song": "Song of Solomon",
    "isaiah": "Isaiah",
    "isa": "Isaiah",
    "jeremiah": "Jeremiah",
    "jer": "Jeremiah",
    "lamentations": "Lamentations",
    "lam": "Lamentations",
    "ezekiel": "Ezekiel",
    "ezek": "Ezekiel",
    "daniel": "Daniel",
    "dan": "Daniel",
    "hosea": "Hosea",
    "hos": "Hosea",
    "joel": "Joel",
    "amos": "Amos",
    "obadiah": "Obadiah",
    "obad": "Obadiah",
    "jonah": "Jonah",
    "micah": "Micah",
    "nahum": "Nahum",
    "habakkuk": "Habakkuk",
    "hab": "Habakkuk",
    "zephaniah": "Zephaniah",
    "zeph": "Zephaniah",
    "haggai": "Haggai",
    "hagg": "Haggai",
    "zechariah": "Zechariah",
    "zech": "Zechariah",
    "malachi": "Malachi",
    "mal": "Malachi",
    "matthew": "Matthew",
    "matt": "Matthew",
    "mt": "Matthew",
    "mark": "Mark",
    "mk": "Mark",
    "luke": "Luke",
    "lk": "Luke",
    "john": "John",
    "jn": "John",
    "acts": "Acts",
    "romans": "Romans",
    "rom": "Romans",
    "1 corinthians": "1 Corinthians",
    "1 cor": "1 Corinthians",
    "2 corinthians": "2 Corinthians",
    "2 cor": "2 Corinthians",
    "galatians": "Galatians",
    "gal": "Galatians",
    "ephesians": "Ephesians",
    "eph": "Ephesians",
    "philippians": "Philippians",
    "phil": "Philippians",
    "colossians": "Colossians",
    "col": "Colossians",
    "1 thessalonians": "1 Thessalonians",
    "1 thess": "1 Thessalonians",
    "2 thessalonians": "2 Thessalonians",
    "2 thess": "2 Thessalonians",
    "1 timothy": "1 Timothy",
    "1 tim": "1 Timothy",
    "2 timothy": "2 Timothy",
    "2 tim": "2 Timothy",
    "titus": "Titus",
    "philemon": "Philemon",
    "phlm": "Philemon",
    "hebrews": "Hebrews",
    "heb": "Hebrews",
    "james": "James",
    "jas": "James",
    "1 peter": "1 Peter",
    "1 pet": "1 Peter",
    "2 peter": "2 Peter",
    "2 pet": "2 Peter",
    "1 john": "1 John",
    "2 john": "2 John",
    "3 john": "3 John",
    "jude": "Jude",
    "revelation": "Revelation",
    "rev": "Revelation",
    
    # French (ZachAI Sovereign Engine)
    "genèse": "Genesis",
    "genese": "Genesis",
    "exode": "Exodus",
    "lévitique": "Leviticus",
    "levitique": "Leviticus",
    "nombres": "Numbers",
    "deutéronome": "Deuteronomy",
    "deuteronome": "Deuteronomy",
    "josué": "Joshua",
    "josue": "Joshua",
    "juges": "Judges",
    "1 samuel": "1 Samuel",
    "2 samuel": "2 Samuel",
    "1 rois": "1 Kings",
    "2 rois": "2 Kings",
    "1 chroniques": "1 Chronicles",
    "2 chroniques": "2 Chronicles",
    "esdras": "Ezra",
    "néhémie": "Nehemiah",
    "nehemie": "Nehemiah",
    "cantique des cantiques": "Song of Solomon",
    "cantique": "Song of Solomon",
    "ésaïe": "Isaiah",
    "esaie": "Isaiah",
    "jérémie": "Jeremiah",
    "jeremie": "Jeremiah",
    "lamentations": "Lamentations",
    "ézéchiel": "Ezekiel",
    "ezechiel": "Ezekiel",
    "osée": "Hosea",
    "osee": "Hosea",
    "sophonie": "Zephaniah",
    "aggée": "Haggai",
    "aggee": "Haggai",
    "zacharie": "Zechariah",
    "malachie": "Malachi",
    "matthieu": "Matthew",
    "marc": "Mark",
    "luc": "Luke",
    "jean": "John",
    "actes": "Acts",
    "romains": "Romans",
    "1 corinthiens": "1 Corinthians",
    "2 corinthiens": "2 Corinthians",
    "galates": "Galatians",
    "éphésiens": "Ephesians",
    "ephesiens": "Ephesians",
    "philippiens": "Philippians",
    "colossiens": "Colossians",
    "1 thessaloniciens": "1 Thessalonians",
    "2 thessaloniciens": "2 Thessalonians",
    "1 timothée": "1 Timothy",
    "1 timothee": "1 Timothy",
    "2 timothée": "2 Timothy",
    "2 timothee": "2 Timothy",
    "tite": "Titus",
    "hébreux": "Hebrews",
    "hebreux": "Hebrews",
    "jacques": "James",
    "1 pierre": "1 Peter",
    "2 pierre": "2 Peter",
    "apocalypse": "Revelation",
    "apoc": "Revelation",
}

_BIBLE_BOOK_PATTERN = "|".join(
    sorted((re.escape(k).replace("\\ ", r"\s+") for k in _BIBLE_BOOK_ALIASES.keys()), key=len, reverse=True)
)
_BIBLE_CITATION_RE = re.compile(
    rf"(?<!\w)(?P<book>{_BIBLE_BOOK_PATTERN})\.?\s+"
    rf"(?P<chapter>\d{{1,3}})\s*:\s*(?P<verse_start>\d{{1,3}})"
    rf"(?:\s*-\s*(?:(?P<range_chapter>\d{{1,3}})\s*:\s*)?(?P<verse_end>\d{{1,3}}))?(?!\w)",
    flags=re.IGNORECASE,
)


def _normalize_bible_book(raw_book: str) -> str:
    key = re.sub(r"\s+", " ", raw_book.strip().lower())
    return _BIBLE_BOOK_ALIASES.get(key, raw_book.strip())


def _detect_biblical_citations(text: str) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for m in _BIBLE_CITATION_RE.finditer(text):
        chapter = int(m.group("chapter"))
        verse_start = int(m.group("verse_start"))
        range_chapter_raw = m.group("range_chapter")
        verse_end_raw = m.group("verse_end")
        if chapter <= 0 or verse_start <= 0:
            continue
        reference = f"{_normalize_bible_book(m.group('book'))} {chapter}:{verse_start}"
        if verse_end_raw:
            verse_end = int(verse_end_raw)
            if verse_end <= 0:
                continue
            if range_chapter_raw:
                range_chapter = int(range_chapter_raw)
                if range_chapter <= 0:
                    continue
                if range_chapter < chapter or (range_chapter == chapter and verse_end < verse_start):
                    continue
                reference += f"-{range_chapter}:{verse_end}"
            else:
                if verse_end < verse_start:
                    continue
                reference += f"-{verse_end}"
        citations.append(
            {
                "reference": reference,
                "start_char": m.start(),
                "end_char": m.end(),
            }
        )
    return citations


async def _export_snapshot_via_worker(body: EditorSnapshotCallbackRequest) -> dict:
    global _export_worker_client
    if _export_worker_client is None:
        raise HTTPException(status_code=503, detail={"error": "Export worker unavailable"})
    if not _SNAPSHOT_CALLBACK_SECRET:
        raise HTTPException(status_code=503, detail={"error": "Snapshot callback is not configured"})
    try:
        resp = await _export_worker_client.post(
            "/snapshot-export",
            json={"document_id": body.document_id, "yjs_state_binary": body.yjs_state_binary},
            headers={
                "X-ZachAI-Snapshot-Secret": _SNAPSHOT_CALLBACK_SECRET,
                "X-Request-ID": request_id_var.get()
            },
        )
    except httpx.RequestError as exc:
        logger.error("snapshot_worker_request_error document_id=%s error=%s", body.document_id, exc)
        raise HTTPException(status_code=502, detail={"error": "Snapshot export worker unreachable"})
    if not (200 <= resp.status_code < 300):
        logger.error(
            "snapshot_worker_http_error document_id=%s status=%s body=%s",
            body.document_id,
            resp.status_code,
            resp.text,
        )
        raise HTTPException(status_code=502, detail={"error": "Snapshot export failed"})
    return resp.json()


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
            headers={"X-Request-ID": request_id_var.get()}
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


async def log_audit_action(
    db: AsyncSession,
    project_id: int,
    user_id: str,
    action: str,
    details: dict,
) -> None:
    """
    Persist an audit log entry (Story 10.4).
    Asynchronous; caller must commit the transaction (usually shared with the main action).
    """
    try:
        # details is dict, AuditLog expects bytes (JSON). Use default=str for non-serializable types.
        details_bytes = json.dumps(details, default=str).encode("utf-8")
        log = AuditLog(
            project_id=project_id,
            user_id=user_id,
            action=action,
            details=details_bytes,
        )
        db.add(log)
        await db.flush()
        logger.info("audit_log_persisted project_id=%s user_id=%s action=%s", project_id, user_id, action)
    except Exception as exc:
        # Audit logging should not crash the main business transaction
        logger.error("audit_log_failed project_id=%s action=%s error=%s", project_id, action, exc)


async def anonymize_user_data(user_id: str, db: AsyncSession) -> None:
    """
    RGPD Right to be Forgotten: Anonymize or purge all data associated with a user (Story 12.1).
    Replicates the logic of the offline cleanup script but for synchronous/admin-triggered use.
    """
    h = hashlib.sha256(f"{user_id}{PLATFORM_SALT}".encode()).hexdigest()[:16]
    anon_id = f"deleted_user_{h}"

    # A. Anonymize Assignments
    await db.execute(
        update(Assignment)
        .where(Assignment.transcripteur_id == user_id)
        .values(transcripteur_id=anon_id)
    )

    # B. Anonymize Audit Logs
    await db.execute(
        update(AuditLog)
        .where(AuditLog.user_id == user_id)
        .values(user_id="ANONYMOUS")
    )

    # C. Anonymize Project Manager (extra safety)
    await db.execute(
        update(Project)
        .where(Project.manager_id == user_id)
        .values(manager_id=anon_id)
    )

    # D. Purge Golden Set (source=frontend_correction)
    # Re-link via the now-anonymized assignments
    sub_stmt = select(Assignment.audio_id).where(Assignment.transcripteur_id == anon_id)
    await db.execute(
        delete(GoldenSetEntry).where(
            GoldenSetEntry.audio_id.in_(sub_stmt),
            GoldenSetEntry.source == "frontend_correction"
        )
    )

    # E. Delete Consent record
    await db.execute(delete(UserConsent).where(UserConsent.user_id == user_id))

    await db.flush()
    logger.info("user_anonymized sub=%s anon=%s", user_id, anon_id)


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
        resp = await _ffmpeg_client.post(
            "/normalize", 
            json=req_body,
            headers={"X-Request-ID": request_id_var.get()}
        )
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


@app.get("/health", tags=["Health"])
def health() -> dict:
    """Docker healthcheck endpoint — unauthenticated."""
    return {"status": "ok"}


@app.post("/v1/upload/request-put", tags=["Presigned uploads"])
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


@app.get("/v1/upload/request-get", tags=["Presigned uploads"])
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


@app.post("/v1/natures", tags=["Natures"], status_code=201)
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


@app.get("/v1/natures", tags=["Natures"])
async def list_natures(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    # Optimization (Story 8.1): Single JOIN + count() instead of N+1 (or selectinload)
    # Accessing n.labels in a loop triggers separate queries.
    stmt = (
        select(Nature, func.count(LabelSchema.id).label("label_count"))
        .outerjoin(LabelSchema)
        .group_by(Nature.id)
    )
    result = await db.execute(stmt)
    natures_with_count = result.all()

    return [
        {
            "id": n.id,
            "name": n.name,
            "description": n.description,
            "created_by": n.created_by,
            "created_at": n.created_at.isoformat(),
            "label_count": count,
        }
        for n, count in natures_with_count
    ]


@app.get("/v1/natures/{nature_id}", tags=["Natures"])
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


@app.put("/v1/natures/{nature_id}/labels", tags=["Natures"])
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


@app.post("/v1/projects", tags=["Projects"], status_code=201)
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
        await db.refresh(project)
        await log_audit_action(
            db,
            project.id,
            creator_id,
            "PROJECT_CREATED",
            {"name": project.name, "nature": nature.name, "production_goal": project.production_goal},
        )
        await db.commit()
        return _project_to_dict(project)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"error": "Project name already exists or data integrity violation"},
        )


@app.get("/v1/projects", tags=["Projects"])
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


@app.get("/v1/projects/{project_id}", tags=["Projects"])
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


@app.put("/v1/projects/{project_id}/status", tags=["Projects"])
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
    if new_status == ProjectStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail={"error": "Use POST /v1/projects/{project_id}/close to complete projects"},
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


@app.post("/v1/projects/{project_id}/close", tags=["Projects"])
async def close_project(
    project_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Close a project when all audios are validated and trigger archival workflow (Story 6.3)."""
    roles = get_roles(payload)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})
    _require_manager_or_admin(roles)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    _require_project_owner_or_admin(project, payload, roles)

    if project.status == ProjectStatus.COMPLETED:
        return {
            "project_id": project.id,
            "status": project.status.value,
            "closed_at": None,
            "idempotent": True,
            "camunda_triggered": False,
            "process_instance_id": project.process_instance_id,
        }

    not_validated = await db.execute(
        select(func.count(AudioFile.id)).where(
            AudioFile.project_id == project_id,
            AudioFile.status != AudioFileStatus.VALIDATED,
        )
    )
    not_validated_count = int(not_validated.scalar_one() or 0)
    if not_validated_count > 0:
        raise HTTPException(
            status_code=409,
            detail={"error": "Project cannot be closed until all audio files are validated"},
        )

    now = datetime.now(timezone.utc)
    state_update = await db.execute(
        update(Project)
        .where(Project.id == project_id, Project.status != ProjectStatus.COMPLETED)
        .values(status=ProjectStatus.COMPLETED)
    )
    if state_update.rowcount != 1:
        # Concurrent close won race; treat as idempotent completion.
        refreshed = await db.execute(select(Project).where(Project.id == project_id))
        current = refreshed.scalar_one_or_none()
        if not current:
            raise HTTPException(status_code=404, detail={"error": "Project not found"})
        return {
            "project_id": current.id,
            "status": current.status.value,
            "closed_at": None,
            "idempotent": True,
            "camunda_triggered": False,
            "process_instance_id": current.process_instance_id,
        }

    await db.commit()

    refreshed = await db.execute(select(Project).where(Project.id == project_id))
    current = refreshed.scalar_one_or_none()
    if not current:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})

    camunda_triggered = False
    process_instance_id: str | None = None
    try:
        audio_count_result = await db.execute(
            select(func.count(AudioFile.id)).where(AudioFile.project_id == project_id)
        )
        audio_count = int(audio_count_result.scalar_one() or 0)
        variables = {
            "projectId": {"value": current.id, "type": "Integer"},
            "managerId": {"value": current.manager_id, "type": "String"},
            "audioCount": {"value": audio_count, "type": "Integer"},
            "closedAt": {"value": now.isoformat(), "type": "String"},
        }
        resp = await camunda_client.post(
            "/process-definition/key/golden-set-archival/start",
            json={"variables": variables, "withVariablesInReturn": True},
        )
        if 200 <= resp.status_code < 300:
            data = resp.json()
            process_instance_id = data.get("id")
            if process_instance_id:
                current.process_instance_id = process_instance_id
                await db.commit()
            camunda_triggered = True
        else:
            logger.error(
                "project_close_camunda_http_error project_id=%s manager_id=%s camunda_status=%s",
                current.id,
                current.manager_id,
                resp.status_code,
            )
    except httpx.RequestError as exc:
        logger.error(
            "project_close_camunda_request_error project_id=%s manager_id=%s error_type=%s",
            current.id,
            current.manager_id,
            type(exc).__name__,
        )
    except ValueError:
        logger.error(
            "project_close_camunda_json_error project_id=%s manager_id=%s",
            current.id,
            current.manager_id,
        )
    logger.info(
        "project_close_handoff project_id=%s manager_id=%s closed_by=%s audio_count=%s camunda_triggered=%s process_instance_id=%s",
        current.id,
        current.manager_id,
        sub,
        audio_count if 'audio_count' in locals() else 0,
        "1" if camunda_triggered else "0",
        process_instance_id or "",
    )
    return {
        "project_id": current.id,
        "status": current.status.value,
        "closed_at": now.isoformat(),
        "idempotent": False,
        "camunda_triggered": camunda_triggered,
        "process_instance_id": process_instance_id,
    }


# ─── Routes — Assignment dashboard (Story 2.4) ───────────────────────────────


@app.get("/v1/projects/{project_id}/audit-trail", tags=["Projects"])
async def get_project_audit_trail(
    project_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list:
    """Project audit log (chronological); Manager owner or Admin."""
    roles = get_roles(payload)
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    _require_project_owner_or_admin(project, payload, roles)

    stmt = (
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await db.execute(stmt)
    logs = res.scalars().all()

    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "details": json.loads(log.details.decode("utf-8")) if log.details else {},
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@app.get("/v1/projects/{project_id}/status", tags=["Projects"])
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


@app.post("/v1/projects/{project_id}/assign", tags=["Projects"])
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


@app.get("/v1/me/profile", tags=["Profile & GDPR"], response_model=UserProfileResponse)
async def get_my_profile(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """User profile with Keycloak claims and RGPD consent status (Story 12.1)."""
    sub = payload.get("sub")
    roles = get_roles(payload)
    
    result = await db.execute(select(UserConsent).where(UserConsent.user_id == sub))
    consent = result.scalar_one_or_none()
    
    if not consent:
        # Lazy initialization on first profile load
        consent = UserConsent(user_id=sub, ml_usage_approved=False, biometric_data_approved=False)
        db.add(consent)
        await db.commit()
        await db.refresh(consent)

    return {
        "sub": sub,
        "name": payload.get("name") or payload.get("preferred_username"),
        "email": payload.get("email"),
        "roles": roles,
        "consents": {
            "ml_usage": consent.ml_usage_approved,
            "biometric_data": consent.biometric_data_approved,
            "deletion_pending": consent.deletion_pending_at is not None,
            "updated_at": consent.updated_at.isoformat(),
        }
    }


@app.put("/v1/me/consents", tags=["Profile & GDPR"], response_model=UserConsentStatus)
async def update_my_consents(
    body: UserConsentUpdate,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Update RGPD consents. Withdraw of ML usage triggers immediate Golden Set purge (Story 12.1)."""
    sub = payload.get("sub")
    
    result = await db.execute(select(UserConsent).where(UserConsent.user_id == sub))
    consent = result.scalar_one_or_none()
    
    if not consent:
        consent = UserConsent(user_id=sub)
        db.add(consent)

    old_ml_usage = consent.ml_usage_approved
    consent.ml_usage_approved = body.ml_usage
    consent.biometric_data_approved = body.biometric_data
    
    await db.commit()
    await db.refresh(consent)

    # Immediate purge logic: if ML consent is withdrawn, delete all Golden Set entries linked to this user.
    if old_ml_usage and not body.ml_usage:
        # Purge frontend corrections specifically (Story 12.1 AC)
        sub_stmt = select(AudioFile.id).join(Assignment).where(Assignment.transcripteur_id == sub)
        purge_stmt = delete(GoldenSetEntry).where(
            GoldenSetEntry.audio_id.in_(sub_stmt),
            GoldenSetEntry.source == "frontend_correction"
        )
        await db.execute(purge_stmt)
        await db.commit()
        logger.info("golden_set_purge_ml_withdrawal user_id=%s source=frontend_correction", sub)

    return {
        "ml_usage": consent.ml_usage_approved,
        "biometric_data": consent.biometric_data_approved,
        "deletion_pending": consent.deletion_pending_at is not None,
        "updated_at": consent.updated_at.isoformat(),
    }


@app.delete("/v1/me/account", tags=["Profile & GDPR"], response_model=UserConsentStatus)
async def request_account_deletion(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Request account deletion (Story 12.1). Sets 48h grace period and blocks API access."""
    sub = payload.get("sub")
    
    result = await db.execute(select(UserConsent).where(UserConsent.user_id == sub))
    consent = result.scalar_one_or_none()
    
    if not consent:
        consent = UserConsent(user_id=sub)
        db.add(consent)

    consent.deletion_pending_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(consent)
    
    logger.info("account_deletion_requested user_id=%s", sub)
    return {
        "ml_usage": consent.ml_usage_approved,
        "biometric_data": consent.biometric_data_approved,
        "deletion_pending": True,
        "updated_at": consent.updated_at.isoformat(),
    }


@app.post("/v1/me/delete-cancel", tags=["Profile & GDPR"], response_model=UserConsentStatus)
async def cancel_account_deletion(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Cancel a pending account deletion request (Story 12.1)."""
    sub = payload.get("sub")
    
    result = await db.execute(select(UserConsent).where(UserConsent.user_id == sub))
    consent = result.scalar_one_or_none()
    
    if not consent or not consent.deletion_pending_at:
        raise HTTPException(status_code=400, detail={"error": "No pending deletion request found"})

    consent.deletion_pending_at = None
    await db.commit()
    await db.refresh(consent)
    
    logger.info("account_deletion_cancelled user_id=%s", sub)
    return {
        "ml_usage": consent.ml_usage_approved,
        "biometric_data": consent.biometric_data_approved,
        "deletion_pending": False,
        "updated_at": consent.updated_at.isoformat(),
    }


@app.delete("/v1/admin/purge-user/{user_id}", tags=["Admin"])
async def admin_purge_user(
    user_id: str,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Admin manual trigger for account anonymization (Story 12.1)."""
    roles = get_roles(payload)
    if "Admin" not in roles:
        raise HTTPException(status_code=403, detail={"error": "Admin role required"})
    
    await anonymize_user_data(user_id, db)
    await db.commit()
    
    return {"status": "purged", "user_id": user_id}


@app.post(
    "/v1/iam/memberships",
    tags=["IAM"],
    responses={
        200: {"description": "Membership already existed for this manager/member pair (idempotent)."},
        201: {"description": "Membership created."},
        400: {"description": "Invalid request (e.g. manager_id equals member_id)."},
        403: {"description": "Admin role required."},
        409: {"description": "Member already mapped to a different manager."},
    },
)
async def post_membership(
    req: ManagerMembershipCreate,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Associate a user to a manager scope (Story 16.2 AC 3). Admin only."""
    roles = get_roles(payload)
    if "Admin" not in roles:
        raise HTTPException(status_code=403, detail={"error": "Admin role required"})

    if req.manager_id == req.member_id:
        raise HTTPException(status_code=400, detail={"error": "manager_id and member_id must be different"})

    r = await db.execute(select(ManagerMembership).where(ManagerMembership.member_id == req.member_id))
    existing = r.scalar_one_or_none()
    if existing:
        if existing.manager_id == req.manager_id:
            body = {
                "id": existing.id,
                "manager_id": existing.manager_id,
                "member_id": existing.member_id,
                "created_at": existing.created_at.isoformat(),
            }
            return JSONResponse(status_code=200, content=body)
        raise HTTPException(status_code=409, detail={"error": "User already belongs to another manager"})

    new_m = ManagerMembership(manager_id=req.manager_id, member_id=req.member_id)
    db.add(new_m)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        r2 = await db.execute(select(ManagerMembership).where(ManagerMembership.member_id == req.member_id))
        existing2 = r2.scalar_one_or_none()
        if existing2 and existing2.manager_id == req.manager_id:
            body = {
                "id": existing2.id,
                "manager_id": existing2.manager_id,
                "member_id": existing2.member_id,
                "created_at": existing2.created_at.isoformat(),
            }
            return JSONResponse(status_code=200, content=body)
        raise HTTPException(status_code=409, detail={"error": "User already belongs to another manager"})

    await db.refresh(new_m)
    body = {
        "id": new_m.id,
        "manager_id": new_m.manager_id,
        "member_id": new_m.member_id,
        "created_at": (new_m.created_at.isoformat() if new_m.created_at else datetime.now(timezone.utc).isoformat()),
    }
    return JSONResponse(status_code=201, content=body)


@app.get("/v1/iam/memberships/{manager_id}", tags=["IAM"])
async def get_memberships(
    manager_id: str,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """List all users in a manager's perimeter (Story 16.2 AC 3). Admin or the manager itself."""
    roles = get_roles(payload)
    sub = payload.get("sub")
    
    if "Admin" not in roles and sub != manager_id:
        raise HTTPException(status_code=403, detail={"error": "Access denied"})
    
    r = await db.execute(select(ManagerMembership).where(ManagerMembership.manager_id == manager_id))
    rows = r.scalars().all()
    
    return [
        {
            "id": row.id,
            "manager_id": row.manager_id,
            "member_id": row.member_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.delete("/v1/iam/memberships/{manager_id}/{member_id}", tags=["IAM"], status_code=204)
async def delete_membership(
    manager_id: str,
    member_id: str,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a user from a manager's perimeter (Story 16.2 AC 3). Admin only."""
    roles = get_roles(payload)
    if "Admin" not in roles:
        raise HTTPException(status_code=403, detail={"error": "Admin role required"})
    
    r = await db.execute(
        delete(ManagerMembership)
        .where(ManagerMembership.manager_id == manager_id)
        .where(ManagerMembership.member_id == member_id)
    )
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": "Membership not found"})
    await db.commit()


@app.post("/v1/iam/users", tags=["IAM"], status_code=201)
async def post_iam_user(
    body: UserCreate,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Create a new user in Keycloak and assign realm role (Story 16.3 AC 1)."""
    roles = get_roles(payload)
    _require_manager_or_admin(roles)
    sub = payload.get("sub")

    # Manager Scope Enforcement
    if "Admin" not in roles:
        if body.role in ("Admin", "Manager"):
            raise HTTPException(
                status_code=403,
                detail={"error": f"Manager cannot create users with role {body.role}"}
            )

    # Prepare Keycloak user data
    user_data = {
        "username": body.username,
        "email": body.email,
        "firstName": body.first_name,
        "lastName": body.last_name,
        "enabled": body.enabled,
    }

    # Create in Keycloak + Role mapping (AC 1, 3)
    new_user_id = await keycloak_admin.create_keycloak_user(user_data, role=body.role)

    # Manager Persistence (Story 16.3 AC 1)
    if "Admin" not in roles:
        try:
            db.add(ManagerMembership(manager_id=sub, member_id=new_user_id))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=409, detail={"error": "Member already mapped to a manager"})
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to persist ManagerMembership for new user %s: %s", new_user_id, exc)
            raise HTTPException(status_code=500, detail={"error": "Failed to persist manager mapping"})

    return {"status": "created", "id": new_user_id}


@app.patch("/v1/iam/users/{user_id}", tags=["IAM"], status_code=204)
async def patch_iam_user(
    user_id: str,
    body: UserUpdate,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Disable/Enable user (Story 16.3 AC 2). Admin or scoped Manager."""
    roles = get_roles(payload)
    _require_manager_or_admin(roles)
    sub = payload.get("sub")

    # Manager Scope Enforcement
    if "Admin" not in roles:
        r = await db.execute(
            select(ManagerMembership)
            .where(ManagerMembership.manager_id == sub)
            .where(ManagerMembership.member_id == user_id)
        )
        membership = r.scalar_one_or_none()
        if not membership:
            raise HTTPException(
                status_code=403,
                detail={"error": "User is outside your scope of management"}
            )

    # Update in Keycloak (AC 2)
    await keycloak_admin.update_keycloak_user(user_id, {"enabled": body.enabled})

    return None


@app.get("/v1/me/export-data", tags=["Profile & GDPR"])
async def export_my_data(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Data portability: stream user data as a ZIP file (Story 12.1 AC 6)."""
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})

    # 0. Redis lock to prevent concurrent exports (AC 2.2)
    if _redis_client is None:
        raise HTTPException(status_code=503, detail={"error": "Redis unavailable"})
    
    lock_key = f"lock:export:{sub}"
    locked = await _redis_client.set(lock_key, "1", nx=True, ex=300) # 5min lock
    if not locked:
        raise HTTPException(status_code=429, detail={"error": "Export already in progress. Please wait."})

    try:
        # 1. Gather profile data
        profile = {
            "sub": sub,
            "name": payload.get("name"),
            "email": payload.get("email"),
            "roles": get_roles(payload),
        }
        r_consent = await db.execute(select(UserConsent).where(UserConsent.user_id == sub))
        consent = r_consent.scalar_one_or_none()
        if consent:
            profile["consents"] = {
                "ml_usage_approved": consent.ml_usage_approved,
                "biometric_data_approved": consent.biometric_data_approved,
                "deletion_pending_at": consent.deletion_pending_at.isoformat() if consent.deletion_pending_at else None,
                "updated_at": consent.updated_at.isoformat(),
            }

        # 2. Gather assignments
        r_asg = await db.execute(
            select(Assignment, AudioFile)
            .join(AudioFile, Assignment.audio_id == AudioFile.id)
            .where(Assignment.transcripteur_id == sub)
        )
        assignments = [
            {
                "audio_id": af.id,
                "filename": af.filename,
                "status": af.status.value,
                "assigned_at": asg.assigned_at.isoformat(),
                "submitted_at": asg.submitted_at.isoformat() if asg.submitted_at else None,
                "validated_at": asg.manager_validated_at.isoformat() if asg.manager_validated_at else None,
            }
            for asg, af in r_asg.all()
        ]

        # 3. Gather corrections (Golden Set entries)
        # Linked via AudioFile assigned to user
        sub_stmt = select(AudioFile.id).join(Assignment).where(Assignment.transcripteur_id == sub)
        r_gse = await db.execute(
            select(GoldenSetEntry).where(GoldenSetEntry.audio_id.in_(sub_stmt))
        )
        corrections = [
            {
                "audio_id": gse.audio_id,
                "segment": [gse.segment_start, gse.segment_end],
                "original_text": gse.original_text,
                "corrected_text": gse.corrected_text,
                "label": gse.label,
                "source": gse.source,
                "created_at": gse.created_at.isoformat(),
            }
            for gse in r_gse.scalars().all()
        ]

        # 4. Gather audit logs
        r_audit = await db.execute(select(AuditLog).where(AuditLog.user_id == sub))
        audit_logs = [
            {
                "project_id": log.project_id,
                "action": log.action,
                "details": json.loads(log.details.decode("utf-8")) if log.details else {},
                "created_at": log.created_at.isoformat(),
            }
            for log in r_audit.scalars().all()
        ]

        def _generate_zip():
            io_buf = io.BytesIO()
            with zipfile.ZipFile(io_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("profile.json", json.dumps(profile, indent=2))
                zf.writestr("assignments.json", json.dumps(assignments, indent=2))
                zf.writestr("corrections.json", json.dumps(corrections, indent=2))
                zf.writestr("audit_logs.json", json.dumps(audit_logs, indent=2))
            
            yield io_buf.getvalue()

        filename = f"export_{sub}_{datetime.now().strftime('%Y%m%d')}.zip"
        return StreamingResponse(
            _generate_zip(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    finally:
        await _redis_client.delete(lock_key)



@app.get("/v1/audio-files/{audio_id}/snapshots", tags=["Snapshots & history"])
async def list_audio_snapshots(
    audio_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    """List available snapshot artifacts for an audio file (Story 12.3 AC 1)."""
    roles = get_roles(payload)
    sub = payload.get("sub")
    
    # Access control: Transcripteur must be assigned, Manager must own project, Admin always.
    result = await db.execute(
        select(AudioFile).where(AudioFile.id == audio_id).options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if "Admin" not in roles:
        if "Manager" in roles:
            pr = await db.execute(select(Project).where(Project.id == af.project_id))
            proj = pr.scalar_one_or_none()
            if not proj or proj.manager_id != sub:
                raise HTTPException(status_code=403, detail={"error": "Not the project owner"})
        else:
            asg = af.assignment
            if not asg or asg.transcripteur_id != sub:
                raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})

    stmt = (
        select(SnapshotArtifact)
        .where(SnapshotArtifact.document_id == audio_id)
        .order_by(SnapshotArtifact.created_at.desc())
    )
    res = await db.execute(stmt)
    snaps = res.scalars().all()

    return [
        {
            "snapshot_id": s.snapshot_id,
            "created_at": s.created_at.isoformat(),
            "source": s.source,
        }
        for s in snaps
    ]


@app.get("/v1/snapshots/{snapshot_id}/yjs", tags=["Snapshots & history"])
async def get_snapshot_yjs(
    snapshot_id: str,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return raw Yjs binary state of a snapshot (Story 12.2 AC 2)."""
    roles = get_roles(payload)
    sub = payload.get("sub")

    stmt = select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id == snapshot_id)
    res = await db.execute(stmt)
    snap = res.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail={"error": "Snapshot not found"})

    # Access control: Transcripteur must be assigned, Manager must own project, Admin always.
    audio_id = snap.document_id
    result = await db.execute(
        select(AudioFile).where(AudioFile.id == audio_id).options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if "Admin" not in roles:
        if "Manager" in roles:
            pr = await db.execute(select(Project).where(Project.id == af.project_id))
            proj = pr.scalar_one_or_none()
            if not proj or proj.manager_id != sub:
                raise HTTPException(status_code=403, detail={"error": "Not the project owner"})
        else:
            asg = af.assignment
            if not asg or asg.transcripteur_id != sub:
                raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})

    # Fetch JSON from MinIO
    try:
        # Snapshots are in 'snapshots' bucket as per _MINIO_BUCKETS and internal_client config
        # SnapshotArtifact.json_object_key already includes 'snapshots/' prefix in some places?
        # Let's check SnapshotArtifact creation in main.py
        # L4860: json_object_key = str(export_out.get("json_object_key") or "")
        # Export worker returns: "json_object_key": f"{SNAPSHOT_BUCKET}/{json_key}"
        # So we need to strip the bucket name if we use internal_client.get_object(bucket, object_name)
        bucket = "snapshots"
        object_key = snap.json_object_key
        if object_key.startswith(f"{bucket}/"):
            object_key = object_key[len(bucket)+1:]

        resp = internal_client.get_object(bucket, object_key)
        data = json.loads(resp.read().decode("utf-8"))
        yjs_b64 = data.get("yjs_state_binary")
        if not yjs_b64:
            raise HTTPException(status_code=502, detail={"error": "Snapshot JSON missing yjs_state_binary"})
        
        yjs_raw = base64.b64decode(yjs_b64.encode("ascii"), validate=True)
        return Response(content=yjs_raw, media_type="application/octet-stream")
    except S3Error as exc:
        logger.error("minio_error snapshot_id=%s error=%s", snapshot_id, exc)
        raise HTTPException(status_code=502, detail={"error": "Failed to fetch snapshot from storage"})
    except Exception as exc:
        logger.error("snapshot_yjs_error snapshot_id=%s error=%s", snapshot_id, exc)
        raise HTTPException(status_code=502, detail={"error": str(exc)})


async def _signal_hocuspocus_reload(audio_id: int):
    """Broadcast reload signal to Hocuspocus instances via Redis Pub/Sub (Story 12.3 AC 1.1)."""
    if _redis_client is not None:
        try:
            msg = json.dumps({"type": "reload", "document_id": audio_id})
            await _redis_client.publish("hocuspocus:signals", msg)
            logger.info("sent_hocuspocus_reload_signal audio_id=%s", audio_id)
        except Exception as exc:
            logger.error("failed_to_signal_hocuspocus audio_id=%s error=%s", audio_id, exc)


def _jwt_display_name(payload: dict) -> str:
    """Human-readable label for collaboration overlays (Story 12.3)."""
    name = (payload.get("name") or "").strip()
    if name:
        return name
    pref = (payload.get("preferred_username") or "").strip()
    if pref:
        return pref
    sub = str(payload.get("sub") or "").strip()
    return sub[:16] if sub else "Collaborator"


async def _publish_hocuspocus_signal(message: dict) -> None:
    """Redis pub/sub on ``hocuspocus:signals`` for Hocuspocus and stateless fan-out (Story 12.3)."""
    if _redis_client is None:
        return
    try:
        await _redis_client.publish("hocuspocus:signals", json.dumps(message))
    except Exception as exc:
        logger.error("hocuspocus_signal_publish_failed msg=%s error=%s", message.get("type"), exc)


# ─── Story 13.1: restore failure signal (Redis → Hocuspocus → zachai:document_restore_failed) ───
# Integrators: JSON on channel ``hocuspocus:signals`` with ``type: "document_restore_failed"``.
# Fields: ``schema_version`` (int, v1), ``document_id`` (int), ``code`` (machine string),
# optional ``message`` (short UI copy; no object keys or stack traces). Bump ``schema_version`` only
# on breaking field renames/removals.

DOCUMENT_RESTORE_FAILED_SCHEMA_VERSION = 1


class DocumentRestoreFailureCode:
    """Stable codes for ``document_restore_failed`` payloads (Story 13.1)."""

    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    AUDIO_NOT_FOUND = "AUDIO_NOT_FOUND"
    SNAPSHOT_FETCH_FAILED = "SNAPSHOT_FETCH_FAILED"
    SNAPSHOT_PAYLOAD_INVALID = "SNAPSHOT_PAYLOAD_INVALID"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    STORAGE_ERROR = "STORAGE_ERROR"
    UNKNOWN = "UNKNOWN"


_KNOWN_DOCUMENT_RESTORE_FAILURE_CODES: frozenset[str] = frozenset(
    {
        DocumentRestoreFailureCode.SNAPSHOT_NOT_FOUND,
        DocumentRestoreFailureCode.AUDIO_NOT_FOUND,
        DocumentRestoreFailureCode.SNAPSHOT_FETCH_FAILED,
        DocumentRestoreFailureCode.SNAPSHOT_PAYLOAD_INVALID,
        DocumentRestoreFailureCode.INTEGRITY_MISMATCH,
        DocumentRestoreFailureCode.STORAGE_ERROR,
        DocumentRestoreFailureCode.UNKNOWN,
    }
)


def _short_restore_public_message(text: str, max_len: int = 240) -> str:
    t = (text or "").strip()
    return t[:max_len] if t else ""


def _restore_failure_public_text_from_detail_piece(value: Any, depth: int = 0) -> str:
    """Flatten a detail fragment for short UI copy (no stack traces, no object dumps)."""
    if value is None or depth > 3:
        return ""
    if isinstance(value, str):
        # Truncate early to avoid memory spikes on massive strings.
        return value[:1024].strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("error", "message", "msg", "detail"):
            if key in value:
                return _restore_failure_public_text_from_detail_piece(value[key], depth + 1)
        return ""
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for item in value:
            s = _restore_failure_public_text_from_detail_piece(item, depth + 1)
            if s:
                parts.append(s)
            if len(parts) >= 10:  # Cap list pieces
                break
        return "; ".join(parts)
    return ""


def _restore_failure_code_from_http_detail(detail: Any) -> str | None:
    if isinstance(detail, dict):
        raw = detail.get("code")
        if isinstance(raw, str):
            c = raw.strip().upper()
            if c in _KNOWN_DOCUMENT_RESTORE_FAILURE_CODES:
                return c
    return None


def _restore_failure_message_from_http_detail(detail: Any) -> str:
    if isinstance(detail, dict):
        structured = _restore_failure_code_from_http_detail(detail) is not None
        for key in ("error", "message", "msg", "detail"):
            if key in detail:
                t = _restore_failure_public_text_from_detail_piece(detail[key])
                if t:
                    return t
        if not structured and detail:
            # Avoid forwarding arbitrary dict keys (may contain internal fields).
            return ""
        return ""
    if isinstance(detail, (str, int, float, bool)):
        return _restore_failure_public_text_from_detail_piece(detail)
    if isinstance(detail, (list, tuple)):
        return _restore_failure_public_text_from_detail_piece(detail)
    # Never fall back to str(detail) to avoid leaking internal object dumps.
    return ""


def _default_restore_failure_code_for_status(status_code: int) -> str:
    if status_code == 404:
        return DocumentRestoreFailureCode.SNAPSHOT_NOT_FOUND
    if status_code == 502:
        return DocumentRestoreFailureCode.STORAGE_ERROR
    if status_code == 423:
        return DocumentRestoreFailureCode.STORAGE_ERROR
    if status_code == 409:
        return DocumentRestoreFailureCode.STORAGE_ERROR
    return DocumentRestoreFailureCode.UNKNOWN


def _document_restore_failed_signal_from_http_exception(audio_id: int, exc: HTTPException, restore_id: str | None = None) -> dict[str, Any]:
    structured = _restore_failure_code_from_http_detail(exc.detail)
    code = structured or _default_restore_failure_code_for_status(exc.status_code)
    message = _short_restore_public_message(_restore_failure_message_from_http_detail(exc.detail))
    out: dict[str, Any] = {
        "type": "document_restore_failed",
        "schema_version": DOCUMENT_RESTORE_FAILED_SCHEMA_VERSION,
        "document_id": audio_id,
        "code": code,
    }
    if restore_id:
        out["restore_id"] = restore_id
    if message:
        out["message"] = message
    return out


def _document_restore_failed_signal(audio_id: int, exc: Exception, restore_id: str | None = None) -> dict[str, Any]:
    """Build Redis JSON for ``document_restore_failed`` before ``document_unlocked`` on failure paths.

    Only ``Exception`` is accepted: restore core uses ``except Exception`` before signaling, so
    ``KeyboardInterrupt`` / ``SystemExit`` never reach this helper.
    """
    if isinstance(exc, HTTPException):
        return _document_restore_failed_signal_from_http_exception(audio_id, exc, restore_id)

    if isinstance(exc, (AttributeError, KeyError, TypeError, ValueError)):
        code = DocumentRestoreFailureCode.SNAPSHOT_PAYLOAD_INVALID
        message = _short_restore_public_message("Snapshot data could not be processed")
    else:
        code = DocumentRestoreFailureCode.UNKNOWN
        message = _short_restore_public_message("Restore failed due to an internal error")

    out: dict[str, Any] = {
        "type": "document_restore_failed",
        "schema_version": DOCUMENT_RESTORE_FAILED_SCHEMA_VERSION,
        "document_id": audio_id,
        "code": code,
    }
    if restore_id:
        out["restore_id"] = restore_id
    if message:
        out["message"] = message
    return out


async def _restore_document_from_snapshot_core(
    *,
    audio_id: int,
    snapshot_id: str,
    payload: dict,
    db: AsyncSession,
) -> dict:
    """
    Story 12.3: shared restore — lock, collaboration signal, MinIO fetch + integrity check, PG swap, reload, unlock.
    Caller must have already authorized write access to the document.
    """
    restore_id = str(uuid.uuid4())
    sub = payload.get("sub")
    display_name = _jwt_display_name(payload)

    if _redis_client is None:
        raise HTTPException(status_code=503, detail={"error": "Redis unavailable"})

    lock_key = f"lock:document:{audio_id}:restoring"
    locked = await _redis_client.set(lock_key, sub or "unknown", nx=True, ex=60)
    if not locked:
        raise HTTPException(
            status_code=423,
            detail={"error": "Restoration already in progress; document is locked."},
        )

    locked_signaled = False
    pending_exc: Exception | None = None
    try:
        await _publish_hocuspocus_signal(
            {
                "type": "document_locked",
                "document_id": audio_id,
                "user_name": display_name,
                "restore_id": restore_id,
            }
        )
        locked_signaled = True

        stmt = select(SnapshotArtifact).where(
            SnapshotArtifact.document_id == audio_id,
            SnapshotArtifact.snapshot_id == snapshot_id,
        )
        r_snap = await db.execute(stmt)
        snap = r_snap.scalar_one_or_none()
        if not snap:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Snapshot not found",
                    "code": DocumentRestoreFailureCode.SNAPSHOT_NOT_FOUND,
                },
            )

        bucket = "snapshots"
        object_key = snap.json_object_key
        if object_key.startswith(f"{bucket}/"):
            object_key = object_key[len(bucket) + 1 :]

        try:
            resp = internal_client.get_object(bucket, object_key)
            data = json.loads(resp.read().decode("utf-8"))
            yjs_b64 = data.get("yjs_state_binary")
            if not yjs_b64:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "Snapshot JSON missing yjs_state_binary",
                        "code": DocumentRestoreFailureCode.SNAPSHOT_PAYLOAD_INVALID,
                    },
                )
            yjs_raw = base64.b64decode(yjs_b64.encode("ascii"), validate=True)
        except S3Error as exc:
            logger.error("minio_error snapshot_id=%s error=%s", snapshot_id, exc)
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "Failed to fetch snapshot from storage",
                    "code": DocumentRestoreFailureCode.SNAPSHOT_FETCH_FAILED,
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("snapshot_yjs_error snapshot_id=%s error=%s", snapshot_id, exc)
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "Snapshot payload could not be read",
                    "code": DocumentRestoreFailureCode.STORAGE_ERROR,
                },
            )

        digest = hashlib.sha256(yjs_raw).hexdigest()
        if digest != snap.yjs_sha256:
            logger.error(
                "snapshot_integrity_mismatch snapshot_id=%s expected=%s got=%s",
                snapshot_id,
                snap.yjs_sha256,
                digest,
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "Snapshot Yjs payload does not match stored integrity hash",
                    "code": DocumentRestoreFailureCode.INTEGRITY_MISMATCH,
                },
            )

        result_af = await db.execute(
            select(AudioFile).where(AudioFile.id == audio_id).options(selectinload(AudioFile.assignment))
        )
        af = result_af.scalar_one_or_none()
        if not af:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Audio file not found",
                    "code": DocumentRestoreFailureCode.AUDIO_NOT_FOUND,
                },
            )

        async with db.begin_nested():
            await db.execute(select(AudioFile).where(AudioFile.id == audio_id).with_for_update())
            await db.execute(delete(YjsLog).where(YjsLog.document_id == audio_id))
            db.add(YjsLog(document_id=audio_id, update_binary=yjs_raw))

        await log_audit_action(
            db,
            af.project_id,
            sub,
            "DOCUMENT_RESTORED",
            {"audio_id": audio_id, "snapshot_id": snapshot_id},
        )
        await db.commit()

        await _signal_hocuspocus_reload(audio_id)

        logger.info("document_restored audio_id=%s snapshot_id=%s user_id=%s", audio_id, snapshot_id, sub)

        await _publish_hocuspocus_signal(
            {
                "type": "document_restored",
                "schema_version": DOCUMENT_RESTORE_FAILED_SCHEMA_VERSION,
                "document_id": audio_id,
                "restore_id": restore_id,
            }
        )

        return {
            "status": "ok",
            "message": "Document restoration successful. Collaborators will be re-synced.",
            "snapshot_id": snapshot_id,
            "restore_id": restore_id,
        }
    except Exception as e:
        pending_exc = e
        raise
    finally:
        if locked_signaled and pending_exc is not None:
            try:
                await _publish_hocuspocus_signal(_document_restore_failed_signal(audio_id, pending_exc, restore_id))
            except Exception:
                logger.error("failed_to_publish_restore_failure_signal audio_id=%s", audio_id)
        
        await _publish_hocuspocus_signal({
            "type": "document_unlocked",
            "document_id": audio_id,
            "restore_id": restore_id,
        })
        await _redis_client.delete(lock_key)


async def _authorize_restore_collaborator_access(
    db: AsyncSession,
    af: AudioFile,
    roles: list[str],
    sub: str | None,
) -> None:
    """Same scope as POST /v1/editor/ticket for Transcripteur / Expert (Story 12.3)."""
    if "Expert" in roles:
        proj_r = await db.execute(select(Project).where(Project.id == af.project_id))
        proj = proj_r.scalar_one_or_none()
        if proj is None or proj.status != ProjectStatus.ACTIVE:
            raise HTTPException(status_code=403, detail={"error": "Project is not active"})
        return
    if "Transcripteur" in roles:
        asg = af.assignment
        if not asg or asg.transcripteur_id != sub:
            raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})
        if af.status not in (AudioFileStatus.ASSIGNED, AudioFileStatus.IN_PROGRESS):
            raise HTTPException(
                status_code=409,
                detail={"error": "Audio file status does not allow editor access"},
            )
        return
    raise HTTPException(
        status_code=403,
        detail={"error": "Transcripteur, Expert, Admin, or Manager role required"},
    )


@app.post("/v1/snapshots/{snapshot_id}/restore", tags=["Snapshots & history"])
async def restore_snapshot_by_id(
    snapshot_id: str,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """POST /v1/snapshots/{snapshot_id}/restore — Story 12.3 AC 1 (canonical REST path)."""
    roles = get_roles(payload)
    sub = payload.get("sub")

    stmt = select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id == snapshot_id)
    r_snap = await db.execute(stmt)
    snap = r_snap.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail={"error": "Snapshot not found"})

    audio_id = snap.document_id

    result = await db.execute(
        select(AudioFile).where(AudioFile.id == audio_id).options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if "Admin" not in roles:
        if "Manager" in roles:
            pr = await db.execute(select(Project).where(Project.id == af.project_id))
            proj = pr.scalar_one_or_none()
            if not proj or proj.manager_id != sub:
                raise HTTPException(status_code=403, detail={"error": "Not the project owner"})
        else:
            await _authorize_restore_collaborator_access(db, af, roles, sub)

    return await _restore_document_from_snapshot_core(
        audio_id=audio_id,
        snapshot_id=snapshot_id,
        payload=payload,
        db=db,
    )


@app.post("/v1/editor/restore/{audio_id}", tags=["Snapshots & history"])
async def restore_document_from_snapshot(
    audio_id: int,
    body: DocumentRestoreRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Restore document state from a snapshot with Redis lock (Story 12.3)."""
    roles = get_roles(payload)
    sub = payload.get("sub")

    result = await db.execute(
        select(AudioFile).where(AudioFile.id == audio_id).options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    if "Admin" not in roles:
        if "Manager" in roles:
            pr = await db.execute(select(Project).where(Project.id == af.project_id))
            proj = pr.scalar_one_or_none()
            if not proj or proj.manager_id != sub:
                raise HTTPException(status_code=403, detail={"error": "Not the project owner"})
        else:
            await _authorize_restore_collaborator_access(db, af, roles, sub)

    return await _restore_document_from_snapshot_core(
        audio_id=audio_id,
        snapshot_id=body.snapshot_id,
        payload=payload,
        db=db,
    )



@app.get("/v1/me/audio-tasks", tags=["Tasks"])
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


@app.get("/v1/expert/tasks", tags=["Tasks"], response_model=list[ExpertTaskResponse])
async def list_expert_tasks(
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    """
    Expert dashboard task list.
    Roles: Expert or Admin.
    Data source: label_studio Golden Set rows joined to audio/project metadata.
    Scope:
    - Admin: full list
    - Expert: only rows mapped to own assignment sub
    """
    roles = get_roles(payload)
    if not {"Expert", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Expert or Admin role required"})
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})

    stmt = (
        select(GoldenSetEntry, AudioFile, Project, Assignment)
        .join(AudioFile, GoldenSetEntry.audio_id == AudioFile.id)
        .join(Project, AudioFile.project_id == Project.id)
        .outerjoin(Assignment, Assignment.audio_id == AudioFile.id)
        .where(GoldenSetEntry.source == "label_studio")
        .order_by(GoldenSetEntry.created_at.desc())
    )
    # Enforce per-user scope for Expert role. Admin keeps global view.
    if "Admin" not in roles:
        stmt = stmt.where(Assignment.transcripteur_id == str(sub))

    result = await db.execute(stmt)
    rows = result.all()
    output: list[dict[str, Any]] = []
    for gse, af, proj, asg in rows:
        # Defensive guard for mocked/fallback DB paths: never leak cross-user rows to Expert.
        if "Admin" not in roles and (not asg or str(asg.transcripteur_id) != str(sub)):
            continue
        output.append(
            {
                "audio_id": af.id,
                "project_id": proj.id,
                "project_name": proj.name,
                "filename": af.filename,
                "status": af.status.value,
                "assigned_at": (
                    asg.assigned_at.isoformat()
                    if asg and getattr(asg, "assigned_at", None)
                    else (gse.created_at.isoformat() if gse.created_at else None)
                ),
                "expert_id": (str(asg.transcripteur_id) if asg else None),
                "source": gse.source,
                "priority": "high" if gse.weight == "high" else "standard",
            }
        )
    return output


# ─── Routes — Audio upload & FFmpeg (Story 2.3) ─────────────────────────────


@app.post("/v1/projects/{project_id}/audio-files/upload", tags=["Project audio"])
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


@app.post("/v1/projects/{project_id}/audio-files/register", tags=["Project audio"], status_code=201)
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
    await log_audit_action(
        db,
        project_id,
        payload.get("sub"),
        "AUDIO_UPLOADED",
        {"filename": filename, "audio_id": audio.id},
    )
    await db.commit()
    await call_ffmpeg_normalize(db, audio)
    await db.refresh(audio)
    return _audio_file_to_dict(audio)


@app.post("/v1/projects/{project_id}/audio-files/{audio_file_id}/normalize", tags=["Project audio"])
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


@app.post("/v1/golden-set/entry", tags=["Golden Set"])
async def post_golden_set_entry(
    request: Request,
    body: GoldenSetEntryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Internal ingest — service API key (not Keycloak). See docs/api-mapping.md §4."""
    verify_golden_set_internal_secret(request)
    return await persist_golden_set_entry(db, body)


@app.get("/v1/golden-set/status", tags=["Golden Set"], response_model=GoldenSetStatusResponse)
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


@app.post("/v1/golden-set/frontend-correction", tags=["Golden Set"])
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


@app.post("/v1/transcriptions/{audio_id}/submit", tags=["Transcription workflow"])
async def submit_transcription(
    audio_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mark assigned transcription as submitted by Transcripteur (Story 6.1)."""
    roles = get_roles(payload)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})
    if not {"Transcripteur", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Transcripteur or Admin role required"})

    result = await db.execute(
        select(AudioFile)
        .where(AudioFile.id == audio_id)
        .options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    asg = af.assignment
    if not asg:
        raise HTTPException(status_code=404, detail={"error": "Assignment not found for audio file"})

    if "Admin" not in roles and asg.transcripteur_id != sub:
        raise HTTPException(status_code=403, detail={"error": "Not assigned to this audio file"})

    if af.status == AudioFileStatus.TRANSCRIBED and asg.submitted_at is not None:
        return {
            "audio_id": af.id,
            "status": af.status.value,
            "submitted_at": asg.submitted_at.isoformat(),
            "idempotent": True,
        }

    if af.status not in (AudioFileStatus.ASSIGNED, AudioFileStatus.IN_PROGRESS):
        raise HTTPException(status_code=409, detail={"error": "Audio file status does not allow submission"})

    now = datetime.now(timezone.utc)
    af.status = AudioFileStatus.TRANSCRIBED
    # Keep submitted_at aligned with the latest successful submit cycle.
    asg.submitted_at = now
    await db.commit()

    logger.info(
        "transcription_submitted audio_id=%s project_id=%s transcripteur_id=%s submitted_at=%s manager_notification_handoff=queued",
        af.id,
        af.project_id,
        asg.transcripteur_id,
        asg.submitted_at.isoformat() if asg.submitted_at else now.isoformat(),
    )
    return {
        "audio_id": af.id,
        "status": af.status.value,
        "submitted_at": asg.submitted_at.isoformat() if asg.submitted_at else now.isoformat(),
        "idempotent": False,
    }


@app.post("/v1/transcriptions/{audio_id}/validate", tags=["Transcription workflow"])
async def validate_transcription(
    audio_id: int,
    body: TranscriptionValidationRequest,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Approve/reject submitted transcription by project owner Manager or Admin (Story 6.2)."""
    roles = get_roles(payload)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})

    _require_manager_or_admin(roles)

    result = await db.execute(
        select(AudioFile)
        .where(AudioFile.id == audio_id)
        .options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    asg = af.assignment
    if not asg:
        raise HTTPException(status_code=404, detail={"error": "Assignment not found for audio file"})

    pr = await db.execute(select(Project).where(Project.id == af.project_id))
    project = pr.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail={"error": "Project not found for audio file"})

    _require_project_owner_or_admin(project, payload, roles)

    now = datetime.now(timezone.utc)
    comment_clean = body.comment.strip() if body.comment else None
    if body.approved:
        state_update = await db.execute(
            update(AudioFile)
            .where(AudioFile.id == af.id, AudioFile.status == AudioFileStatus.TRANSCRIBED)
            .values(status=AudioFileStatus.VALIDATED)
        )
        if state_update.rowcount != 1:
            raise HTTPException(status_code=409, detail={"error": "Audio file status does not allow validation"})
        af.status = AudioFileStatus.VALIDATED
        asg.manager_validated_at = now
    else:
        if not comment_clean:
            raise HTTPException(status_code=400, detail={"error": "Comment is required when approved is false"})
        state_update = await db.execute(
            update(AudioFile)
            .where(AudioFile.id == af.id, AudioFile.status == AudioFileStatus.TRANSCRIBED)
            .values(status=AudioFileStatus.ASSIGNED)
        )
        if state_update.rowcount != 1:
            raise HTTPException(status_code=409, detail={"error": "Audio file status does not allow validation"})
        af.status = AudioFileStatus.ASSIGNED
        asg.submitted_at = None
        asg.manager_validated_at = None

    await db.commit()

    await log_audit_action(
        db,
        project.id,
        sub,
        "TRANSCRIPTION_VALIDATED" if body.approved else "TRANSCRIPTION_REJECTED",
        {
            "audio_id": af.id,
            "filename": af.filename,
            "motif": comment_clean if not body.approved else None,
        },
    )
    await db.commit()

    logger.info(
        "transcription_validation_handoff audio_id=%s project_id=%s manager_id=%s transcripteur_id=%s approved=%s status=%s comment_present=%s comment_length=%s validated_at=%s",
        af.id,
        af.project_id,
        sub,
        asg.transcripteur_id,
        "1" if body.approved else "0",
        af.status.value,
        "1" if comment_clean else "0",
        len(comment_clean) if comment_clean else 0,
        asg.manager_validated_at.isoformat() if asg.manager_validated_at else "",
    )

    return {
        "audio_id": af.id,
        "status": af.status.value,
        "approved": body.approved,
        "comment": comment_clean,
        "manager_validated_at": asg.manager_validated_at.isoformat() if asg.manager_validated_at else None,
    }


@app.get("/v1/audio-files/{audio_file_id}/transcription", tags=["Transcription workflow"])
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


# ─── Routes — Export transcript/subtitle (Story 7.1) ─────────────────────────


@app.get("/v1/export/subtitle/{audio_id}", tags=["Export"])
async def export_subtitle(
    audio_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query(..., description="Export format; Story 7.1 supports only srt"),
) -> Response:
    roles = get_roles(payload)
    if format != "srt":
        raise HTTPException(status_code=422, detail={"error": "Invalid format. Expected 'srt'"})

    af = await _resolve_audio_for_export(db, audio_id, payload, roles)
    if af.status != AudioFileStatus.VALIDATED:
        raise HTTPException(status_code=409, detail={"error": "Audio file status must be validated for export"})

    _, snapshot_payload = await _load_latest_snapshot_payload(db, audio_id)
    try:
        segments = _extract_segments_from_snapshot(snapshot_payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    if not segments:
        raise HTTPException(status_code=404, detail={"error": "No transcription segments available for export"})

    try:
        srt_content = _build_srt_content(segments)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})

    stem = _sanitize_export_stem(af.filename, f"audio_{audio_id}")
    filename = f"{stem}_{audio_id}.srt"
    return Response(
        content=srt_content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/v1/export/transcript/{audio_id}", tags=["Export"])
async def export_transcript(
    audio_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query(..., description="Export format: txt|docx"),
) -> Response:
    roles = get_roles(payload)
    if format not in {"txt", "docx"}:
        raise HTTPException(status_code=422, detail={"error": "Invalid format. Expected 'txt' or 'docx'"})

    af = await _resolve_audio_for_export(db, audio_id, payload, roles)
    if af.status != AudioFileStatus.VALIDATED:
        raise HTTPException(status_code=409, detail={"error": "Audio file status must be validated for export"})

    if format == "txt":
        _, snapshot_payload = await _load_latest_snapshot_payload(db, audio_id)
        try:
            segments = _extract_segments_from_snapshot(snapshot_payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc)})
        transcript_text = _extract_text_from_snapshot(snapshot_payload, segments)
        if not transcript_text:
            raise HTTPException(status_code=404, detail={"error": "No transcription text available for export"})
    stem = _sanitize_export_stem(af.filename, f"audio_{audio_id}")
    if format == "txt":
        filename = f"{stem}_{audio_id}.txt"
        return Response(
            content=(transcript_text + ("\n" if transcript_text else "")).encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    snap = await _load_latest_snapshot_artifact(db, audio_id)
    filename = f"{stem}_{audio_id}.docx"
    bucket, obj = _parse_bucket_and_object(snap.docx_object_key)
    try:
        resp = internal_client.get_object(bucket, obj)
        docx_bytes = resp.read()
        resp.close()
        resp.release_conn()
    except S3Error:
        raise HTTPException(status_code=503, detail={"error": "MinIO unavailable"})
    except Exception:
        raise HTTPException(status_code=502, detail={"error": "Snapshot DOCX fetch failed"})
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/v1/whisper/transcribe", tags=["Open APIs"])
async def post_whisper_transcribe(
    body: WhisperOpenApiRequest,
    request: Request,
) -> dict[str, Any]:
    """External Whisper transcription API (Story 7.2)."""
    verify_whisper_open_api_key(request)

    audio_bytes, content_type = await _fetch_whisper_source_audio(body.audio_url)
    bucket, obj_key = _stage_whisper_audio_to_minio(audio_bytes, content_type)
    try:
        upstream = await _call_openvino_transcribe(bucket, obj_key)
    finally:
        try:
            internal_client.remove_object(bucket, obj_key)
        except Exception:
            logger.warning("whisper_open_api cleanup_failed bucket=%s key=%s", bucket, obj_key)
    segments = _normalize_openvino_segments(upstream.get("segments"))

    duration_s = max((float(seg["end"]) for seg in segments), default=0.0)
    if duration_s > WHISPER_OPEN_API_MAX_DURATION_S:
        raise HTTPException(status_code=422, detail={"error": "transcription duration exceeds allowed maximum"})

    out: dict[str, Any] = {"segments": segments, "duration_s": duration_s}
    if body.language:
        out["language_detected"] = body.language
    if isinstance(upstream.get("model_version"), str):
        out["model_version"] = upstream["model_version"]
    return out


@app.post("/v1/nlp/detect-citations", tags=["Open APIs"])
async def post_detect_citations(
    body: CitationDetectRequest,
    request: Request,
) -> dict[str, Any]:
    """External biblical citation detection API (Story 7.3)."""
    verify_whisper_open_api_key(request)
    return {"citations": _detect_biblical_citations(body.text)}


# ─── Routes — Audio media URL (Story 5.3) ─────────────────────────────────────


@app.get("/v1/audio-files/{audio_file_id}/media", tags=["Media"])
async def get_audio_media(
    audio_file_id: int,
    payload: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return a presigned MinIO URL for normalized audio playback (Story 5.3)."""
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
        .where(AudioFile.id == audio_file_id)
        .options(selectinload(AudioFile.assignment))
    )
    af = result.scalar_one_or_none()
    if not af:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    # Match editor permission gates (Story 5.2): assignment + status for Transcripteur, project active for Expert.
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

    # Normalized audio must exist and be free of validation errors.
    if not _audio_normalized_eligible(af):
        raise HTTPException(
            status_code=409,
            detail={"error": "Audio is not eligible for playback (missing normalized audio)"},
        )

    bucket_name, object_name = _parse_bucket_and_object(af.normalized_path)
    try:
        presigned_url = presigned_client.presigned_get_object(
            bucket_name=bucket_name,
            object_name=object_name,
            expires=timedelta(hours=1),
        )
    except Exception as exc:
        logger.error("MinIO presigned_get_object failed: %s", exc)
        raise HTTPException(status_code=503, detail={"error": "MinIO unavailable"})

    return {"presigned_url": presigned_url, "expires_in": 3600}


@app.post("/v1/proxy/grammar", tags=["Editor & collaboration"])
async def post_proxy_grammar(
    body: GrammarProxyRequest,
    payload: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Proxy spelling/grammar check to LanguageTool (Story 5.5).
    Cached in Redis (TTL GRAMMAR_CACHE_TTL_SEC) keyed by SHA-256(text)+language.
    """
    roles = get_roles(payload)
    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})
    if not {"Transcripteur", "Expert", "Admin"}.intersection(roles):
        raise HTTPException(
            status_code=403,
            detail={"error": "Transcripteur, Expert, or Admin role required"},
        )
    if _redis_client is not None and GRAMMAR_RATE_LIMIT_PER_MIN > 0:
        rl_key = _grammar_rate_limit_key(str(payload.get("sub")))
        try:
            count = await _redis_client.incr(rl_key)
            if count == 1:
                await _redis_client.expire(rl_key, 60)
            if count > GRAMMAR_RATE_LIMIT_PER_MIN:
                raise HTTPException(
                    status_code=429,
                    detail={"error": "Too many grammar requests; retry shortly", "matches": []},
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("grammar_proxy rate limit unavailable: %s", exc)

    text = body.text
    if len(text) > GRAMMAR_MAX_TEXT_LEN:
        raise HTTPException(
            status_code=422,
            detail={"error": "text exceeds maximum length", "max": GRAMMAR_MAX_TEXT_LEN},
        )
    if not _is_internal_languagetool_url(_LANGUAGETOOL_BASE_URL):
        raise HTTPException(
            status_code=503,
            detail={"error": "Grammar service misconfigured (must use internal URL)", "matches": []},
        )

    cache_key = _grammar_cache_key(text, body.language)
    lock_key = f"{cache_key}:fetch"
    lock_token = uuid.uuid4().hex
    lock_ttl_sec = max(5, min(120, int(math.ceil(GRAMMAR_HTTP_TIMEOUT + 10.0))))
    follower_wait_sec = max(2.0, min(120.0, GRAMMAR_HTTP_TIMEOUT + 5.0))
    t0 = time.perf_counter()

    async def _grammar_cache_read() -> dict[str, Any] | None:
        if _redis_client is None or GRAMMAR_CACHE_TTL_SEC <= 0:
            return None
        try:
            raw = await _redis_client.get(cache_key)
            if raw:
                data = json.loads(raw)
                if _grammar_cached_payload_valid(data):
                    return data
                try:
                    await _redis_client.delete(cache_key)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("grammar_proxy cache read failed: %s", exc)
        return None

    lock_held_local: dict[str, bool] = {"v": False}

    async def _grammar_release_lock() -> None:
        if not lock_held_local["v"] or _redis_client is None:
            return
        try:
            await _redis_client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                1,
                lock_key,
                lock_token,
            )
        except Exception as exc:
            logger.warning("grammar_proxy cache lock release failed: %s", exc)
        finally:
            lock_held_local["v"] = False

    hit = await _grammar_cache_read()
    if hit is not None:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "grammar_proxy cache_hit duration_ms=%.1f language=%s",
            elapsed_ms,
            body.language,
        )
        return hit

    if _redis_client is not None and GRAMMAR_CACHE_TTL_SEC > 0:
        try:
            got = await _redis_client.set(lock_key, lock_token, nx=True, ex=lock_ttl_sec)
            lock_held_local["v"] = got is True
        except Exception as exc:
            logger.warning("grammar_proxy cache lock acquire failed: %s", exc)
            lock_held_local["v"] = False
        if not lock_held_local["v"]:
            wait_deadline = time.monotonic() + follower_wait_sec
            while time.monotonic() < wait_deadline:
                await asyncio.sleep(0.1)
                cw = await _grammar_cache_read()
                if cw is not None:
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    logger.info(
                        "grammar_proxy cache_hit_coalesced duration_ms=%.1f language=%s",
                        elapsed_ms,
                        body.language,
                    )
                    return cw
                try:
                    if not await _redis_client.exists(lock_key):
                        break
                except Exception:
                    break
            try:
                lock_still_held = await _redis_client.exists(lock_key)
            except Exception:
                lock_still_held = 0
            if lock_still_held:
                raise HTTPException(
                    status_code=503,
                    detail={"error": "Grammar check in progress for same content; retry shortly", "matches": []},
                )
            try:
                got = await _redis_client.set(lock_key, lock_token, nx=True, ex=lock_ttl_sec)
                lock_held_local["v"] = got is True
            except Exception:
                lock_held_local["v"] = False
            if not lock_held_local["v"]:
                raise HTTPException(
                    status_code=503,
                    detail={"error": "Grammar check in progress for same content; retry shortly", "matches": []},
                )
        else:
            cw = await _grammar_cache_read()
            if cw is not None:
                await _grammar_release_lock()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "grammar_proxy cache_hit duration_ms=%.1f language=%s",
                    elapsed_ms,
                    body.language,
                )
                return cw

    url = f"{_LANGUAGETOOL_BASE_URL}/v2/check"
    try:
        try:
            async with httpx.AsyncClient(timeout=GRAMMAR_HTTP_TIMEOUT) as client:
                r = await client.post(
                    url,
                    data={"text": text, "language": body.language},
                )
        except httpx.TimeoutException:
            logger.warning("grammar_proxy upstream timeout url=%s", url)
            raise HTTPException(
                status_code=503,
                detail={"error": "Grammar service timeout", "matches": []},
            )
        except httpx.RequestError as exc:
            logger.warning("grammar_proxy upstream request_error url=%s err=%s", url, exc)
            raise HTTPException(
                status_code=503,
                detail={"error": "Grammar service unavailable", "matches": []},
            )

        if r.status_code == 429:
            fallback = _basic_regex_matches(text)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Grammar service rate-limited; partial local checks only",
                    "matches": fallback,
                    "degraded": True,
                },
            )

        if r.status_code >= 400:
            logger.warning("grammar_proxy upstream status=%s body_prefix=%s", r.status_code, r.text[:200])
            raise HTTPException(
                status_code=502,
                detail={"error": "Grammar upstream error", "matches": []},
            )

        try:
            data = r.json()
        except Exception:
            raise HTTPException(
                status_code=502,
                detail={"error": "Invalid grammar upstream response", "matches": []},
            )
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=502,
                detail={"error": "Invalid grammar upstream response", "matches": []},
            )

        matches = _normalize_lt_matches(data.get("matches") or [], text)
        out: dict[str, Any] = {"matches": matches, "degraded": False}
        if _redis_client is not None and GRAMMAR_CACHE_TTL_SEC > 0:
            try:
                await _redis_client.setex(cache_key, GRAMMAR_CACHE_TTL_SEC, json.dumps(out))
            except Exception as exc:
                logger.warning("grammar_proxy cache write failed: %s", exc)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "grammar_proxy cache_miss duration_ms=%.1f upstream_status=%s language=%s match_count=%s",
            elapsed_ms,
            r.status_code,
            body.language,
            len(matches),
        )
        return out
    finally:
        await _grammar_release_lock()


@app.post("/v1/editor/ticket", tags=["Editor & collaboration"])
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
    logger.info(
        "editor_ticket auth debug sub=%s roles=%s realm_roles=%s resource_access_clients=%s",
        sub,
        roles,
        ((payload.get("realm_access") or {}).get("roles") if isinstance(payload.get("realm_access"), dict) else None),
        (
            list(payload.get("resource_access", {}).keys())
            if isinstance(payload.get("resource_access"), dict)
            else []
        ),
    )
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "Subject missing in token"})
    if not {"Transcripteur", "Expert", "Admin"}.intersection(roles):
        raise HTTPException(
            status_code=403,
            detail={"error": "Transcripteur, Expert, or Admin role required"},
        )

    # Story 12.3 AC 1.2: Conflict Prevention
    if _redis_client is not None:
        lock_key = f"lock:document:{body.document_id}:restoring"
        if await _redis_client.exists(lock_key):
            raise HTTPException(
                status_code=423,
                detail={"error": "Document is currently being restored and is locked."}
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


@app.post("/v1/editor/callback/snapshot", tags=["Editor & collaboration"])
async def post_editor_snapshot_callback(
    request: Request,
    body: EditorSnapshotCallbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Hocuspocus idle snapshot callback (Story 5.4).
    Secured with shared secret; forwards to export-worker then persists snapshot metadata.
    """
    verify_snapshot_callback_secret(request)

    # Ensure document exists (document_id == audio_files.id by design).
    af_result = await db.execute(select(AudioFile).where(AudioFile.id == body.document_id))
    af = af_result.scalar_one_or_none()
    if af is None:
        raise HTTPException(status_code=404, detail={"error": "Audio file not found"})

    t0 = time.perf_counter()
    export_out = await _export_snapshot_via_worker(body)

    snapshot_id = str(export_out.get("snapshot_id") or "")
    json_object_key = str(export_out.get("json_object_key") or "")
    docx_object_key = str(export_out.get("docx_object_key") or "")
    yjs_sha = str(export_out.get("yjs_sha256") or "")
    json_sha = str(export_out.get("json_sha256") or "")
    docx_sha = str(export_out.get("docx_sha256") or "")
    if not all([snapshot_id, json_object_key, docx_object_key, yjs_sha, json_sha, docx_sha]):
        raise HTTPException(status_code=502, detail={"error": "Snapshot export returned incomplete payload"})

    db.add(
        SnapshotArtifact(
            snapshot_id=snapshot_id,
            document_id=body.document_id,
            json_object_key=json_object_key,
            docx_object_key=docx_object_key,
            yjs_sha256=yjs_sha,
            json_sha256=json_sha,
            docx_sha256=docx_sha,
            source="hocuspocus-idle-callback",
        )
    )
    await db.commit()

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "snapshot_callback_ok document_id=%s snapshot_id=%s json_key=%s docx_key=%s duration_ms=%.0f",
        body.document_id,
        snapshot_id,
        json_object_key,
        docx_object_key,
        elapsed_ms,
    )
    return {"status": "ok", "snapshot_id": snapshot_id}


@app.post("/v1/callback/expert-validation", tags=["Webhooks & callbacks"])
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


@app.post("/v1/callback/model-ready", tags=["Webhooks & callbacks"])
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


# ─── Routes — Bible Engine (Story 11.5) ──────────────────────────────────────


def _bible_verse_cache_key(
    gen: int,
    translation_upper: str,
    ref: str,
    book_norm: str,
    chapter: int,
    verse_start: int,
    verse_end: int | None,
) -> str:
    """Stable Redis key: generation + SHA-256 of request + normalized lookup (Story 13.2)."""
    ve = "" if verse_end is None else str(verse_end)
    canonical = f"{translation_upper}\t{ref}\t{book_norm}\t{chapter}\t{verse_start}\t{ve}"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{BIBLE_VERSE_CACHE_KEY_PREFIX}{gen}:{digest}"


def _bible_verse_cached_payload_valid(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if "reference" not in data or "translation" not in data or "verses" not in data:
        return False
    if not isinstance(data["verses"], list):
        return False
    return True


async def _bible_verse_generation_read(translation_upper: str) -> int:
    if _redis_client is None:
        return 0
    try:
        raw = await _redis_client.get(f"{BIBLE_VERSE_GEN_PREFIX}{translation_upper}")
        if raw is None:
            return 0
        return int(raw)
    except (TypeError, ValueError):
        return 0
    except Exception as exc:
        logger.warning("bible_verse_cache gen read failed translation=%s: %s", translation_upper, exc)
        return 0


@app.get("/v1/bible/verses", tags=["Bible"], response_model=BibleRetrievalResponse)
async def get_bible_verses(
    ref: str = Query(..., description="Bible reference, e.g. 'Jean 3:16' or 'Gen 1:1-5'"),
    translation: str = Query("LSG", description="Translation code (LSG, KJV, etc.)"),
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore
    payload: Annotated[dict, Depends(get_current_user)] = None,  # type: ignore
) -> dict:
    """Retrieve biblical verses from the local sovereign database (Story 11.5 AC2)."""
    if db is None or payload is None: # Should not happen with FastAPI Depends
         raise HTTPException(status_code=500, detail="Dependency injection failed")
    # Any authenticated user can query the Bible.
    m = _BIBLE_CITATION_RE.search(ref)
    if not m:
        # Fallback to a very loose parse if the strict one fails, or just 404.
        # Strict match ensures normalized lookups.
        raise HTTPException(
            status_code=400,
            detail={"error": f"Could not parse reference format: '{ref}'. Use format 'Book Chapter:Verse'"}
        )

    book_raw = m.group("book")
    chapter = int(m.group("chapter"))
    verse_start = int(m.group("verse_start"))
    verse_end_raw = m.group("verse_end")

    book_norm = _normalize_bible_book(book_raw)
    translation_upper = translation.upper()
    verse_end: int | None = int(verse_end_raw) if verse_end_raw else None

    cache_key: str | None = None
    if BIBLE_VERSE_CACHE_ENABLED and BIBLE_VERSE_CACHE_TTL_SEC > 0 and _redis_client is not None:
        gen = await _bible_verse_generation_read(translation_upper)
        cache_key = _bible_verse_cache_key(
            gen, translation_upper, ref, book_norm, chapter, verse_start, verse_end
        )
        try:
            raw = await _redis_client.get(cache_key)
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
                if data is not None and _bible_verse_cached_payload_valid(data):
                    logger.debug("bible_verse_cache_hit translation=%s", translation_upper)
                    return data
                try:
                    await _redis_client.delete(cache_key)
                except Exception as exc:
                    logger.warning("bible_verse_cache corrupt entry delete failed: %s", exc)
            else:
                logger.debug("bible_verse_cache_miss translation=%s", translation_upper)
        except Exception as exc:
            logger.warning("bible_verse_cache read failed: %s", exc)

    stmt = (
        select(BibleVerse)
        .where(
            BibleVerse.translation == translation_upper,
            BibleVerse.book == book_norm,
            BibleVerse.chapter == chapter
        )
    )

    if verse_end is not None:
        # Handle ranges within the same chapter.
        stmt = stmt.where(BibleVerse.verse.between(verse_start, verse_end))
    else:
        stmt = stmt.where(BibleVerse.verse == verse_start)

    stmt = stmt.order_by(BibleVerse.verse)

    result = await db.execute(stmt)
    verses = result.scalars().all()

    if not verses:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Reference '{ref}' not found in {translation} translation"}
        )

    out: dict[str, Any] = {
        "reference": ref,
        "translation": translation_upper,
        "verses": [{"verse": v.verse, "text": v.text} for v in verses],
    }

    if cache_key is not None and _redis_client is not None:
        try:
            await _redis_client.setex(
                cache_key, BIBLE_VERSE_CACHE_TTL_SEC, json.dumps(out, ensure_ascii=False)
            )
        except Exception as exc:
            logger.warning("bible_verse_cache write failed: %s", exc)

    return out


@app.post("/v1/bible/ingest", tags=["Bible"], status_code=201)
async def post_bible_ingest(
    body: BibleIngestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> dict:
    """
    Bulk ingest biblical verses. Protected by internal secret (Story 11.5 AC3).
    Used by CLI ingestion script.
    """
    verify_golden_set_internal_secret(request)
    
    t0 = time.perf_counter()
    
    # Batch UPSERT using PostgreSQL ON CONFLICT (idempotency).
    # Unique constraint expected on (translation, book, chapter, verse).
    # Note: BibleVerse model needs this constraint if not already present.
    
    written = 0
    try:
        # Normalize and prepare values
        rows = []
        for v in body.verses:
            rows.append({
                "translation": v.translation.upper(),
                "book": _normalize_bible_book(v.book),
                "chapter": v.chapter,
                "verse": v.verse,
                "text": v.text
            })
            
        # SQLAlchemy Core for efficient bulk insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        
        stmt = pg_insert(BibleVerse).values(rows)
        # If record exists, update the text.
        stmt = stmt.on_conflict_do_update(
            index_elements=["translation", "book", "chapter", "verse"],
            set_={"text": stmt.excluded.text}
        )
        
        res = await db.execute(stmt)
        await db.commit()
        written = len(body.verses)

        # Story 13.2: bump generation per translation so GET /v1/bible/verses cache keys rotate
        if BIBLE_VERSE_CACHE_ENABLED and BIBLE_VERSE_CACHE_TTL_SEC > 0 and _redis_client is not None:
            seen_tr: set[str] = set()
            for v in body.verses:
                tu = v.translation.upper()
                if tu in seen_tr:
                    continue
                seen_tr.add(tu)
                try:
                    await _redis_client.incr(f"{BIBLE_VERSE_GEN_PREFIX}{tu}")
                except Exception as exc:
                    logger.warning("bible_verse_cache gen incr failed translation=%s: %s", tu, exc)

    except Exception as exc:
        await db.rollback()
        logger.error("bible_ingest_failed error=%s", exc)
        raise HTTPException(status_code=500, detail={"error": f"Ingestion failed: {str(exc)}"})

    ms = (time.perf_counter() - t0) * 1000.0
    logger.info("bible_ingest_ok count=%d duration_ms=%.0f", written, ms)
    
    return {"status": "ok", "count": written}
