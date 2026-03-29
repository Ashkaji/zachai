"""
ZachAI FastAPI Gateway — Story 2.2: Project Creation & Label Studio Provisioning
Extends Story 2.1: Nature CRUD + Story 1.3: Presigned URL Engine + JWT (Keycloak) + MinIO.
Adds: Project + AudioFile ORM, Project CRUD endpoints, Camunda 7 BPMN deployment & process start.
FastAPI never touches audio binary data — upload goes directly browser→MinIO.
"""
import os
import logging
import html
from contextlib import asynccontextmanager
from datetime import timedelta, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, AsyncGenerator
from urllib.parse import quote_plus

import httpx
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from minio import Minio
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, Integer, Float, ForeignKey, DateTime, func, select, delete
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

CAMUNDA_REST_URL: str = os.environ.get("CAMUNDA_REST_URL", "http://camunda7:8080/engine-rest")
camunda_client = httpx.AsyncClient(base_url=CAMUNDA_REST_URL, timeout=30.0)


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
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
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
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
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
    global _jwks_cache
    # JWKS (existing) — tolerant: Keycloak may still be starting
    try:
        _jwks_cache = await fetch_jwks(KEYCLOAK_ISSUER)
        logger.info("JWKS loaded: %d key(s)", len(_jwks_cache.get("keys", [])))
    except Exception as exc:
        logger.error(
            "Failed to load JWKS from Keycloak: %s — JWT verification will fail until Keycloak is reachable",
            exc,
        )

    # DB tables — tolerant: PostgreSQL may not be ready yet
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

    yield

    await engine.dispose()
    await camunda_client.aclose()


app = FastAPI(
    title="ZachAI Gateway",
    description="Lean API gateway: presigned URLs, JWT, Nature CRUD, Project CRUD, Camunda 7",
    version="2.2.0",
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

    # Check duplicate project name
    result = await db.execute(select(Project).where(Project.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail={"error": "Project name already exists"})

    creator_id = payload.get("sub", payload.get("preferred_username"))
    if not creator_id:
        raise HTTPException(status_code=401, detail={"error": "Creator identifier missing in token"})

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
            label_schema_xml = generate_label_studio_xml(nature.labels)
            try:
                etree.fromstring(label_schema_xml.encode())
            except etree.XMLSyntaxError as xml_err:
                logger.error("Generated label_studio_schema is invalid XML: %s", xml_err)
                # Skip Camunda — project is still created successfully
                await db.commit()
                await db.refresh(project)
                return _project_to_dict(project)

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
                project.process_instance_id = resp.json().get("id")
                logger.info("Camunda process started: %s", project.process_instance_id)
            else:
                logger.error(
                    "Camunda start failed: %s — project created but workflow not triggered",
                    resp.status_code,
                )
        except Exception as exc:
            logger.error(
                "Exception starting Camunda process: %s — project created but workflow not triggered",
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
) -> list:
    roles = get_roles(payload)
    if not {"Manager", "Admin"}.intersection(roles):
        raise HTTPException(status_code=403, detail={"error": "Manager or Admin role required"})

    result = await db.execute(select(Project))
    projects = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "nature_name": p.nature.name,
            "status": p.status.value,
            "manager_id": p.manager_id,
            "created_at": p.created_at.isoformat(),
        }
        for p in projects
    ]


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
