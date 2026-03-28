"""
ZachAI FastAPI Gateway — Story 1.3: Presigned URL Engine
Lean gateway: JWT verification (Keycloak) + Presigned URL generation (MinIO).
FastAPI never touches audio binary data — upload goes directly browser→MinIO.
"""
import os
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from minio import Minio
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Env var validation ───────────────────────────────────────────────────────

REQUIRED_ENV_VARS = [
    "KEYCLOAK_ISSUER",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_PRESIGNED_ENDPOINT",
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

# Internal client — connects to minio:9000 (Docker network) for admin ops (bucket existence checks).
internal_client = Minio(
    endpoint=MINIO_INTERNAL_ENDPOINT,
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=MINIO_SECURE,
)

# Presigned URL client — uses the externally reachable endpoint (localhost:9000).
# Region cache is pre-seeded so the SDK generates signed URLs without making any network call.
# SigV4 signature will include 'host:localhost:9000' — valid for browser-to-MinIO uploads.
presigned_client = Minio(
    endpoint=MINIO_PRESIGNED_ENDPOINT,
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,  # localhost is never TLS in dev
)
presigned_client._region_map = {bucket: _MINIO_REGION for bucket in _MINIO_BUCKETS}

# JWKS cache — populated at startup, avoids per-request Keycloak calls
_jwks_cache: dict = {}

# ─── JWKS fetch ───────────────────────────────────────────────────────────────


async def fetch_jwks(issuer: str) -> dict:
    """Fetch public JWKS from Keycloak at startup. Cached for lifetime of process."""
    jwks_url = f"{issuer}/protocol/openid-connect/certs"
    logger.info("Fetching JWKS from %s", jwks_url)
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


# ─── Application lifespan ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _jwks_cache
    try:
        _jwks_cache = await fetch_jwks(KEYCLOAK_ISSUER)
        logger.info("JWKS loaded: %d key(s)", len(_jwks_cache.get("keys", [])))
    except Exception as exc:
        logger.error("Failed to load JWKS from Keycloak: %s — JWT verification will fail until Keycloak is reachable", exc)
        # Do not crash — Keycloak may still be starting; requests will fail auth until JWKS loads
    yield


app = FastAPI(
    title="ZachAI Gateway",
    description="Lean API gateway: presigned URL generation + JWT verification",
    version="1.3.0",
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


# ─── Schemas ──────────────────────────────────────────────────────────────────


class PutRequestBody(BaseModel):
    project_id: str
    filename: str
    content_type: str


# ─── Routes ───────────────────────────────────────────────────────────────────


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
    object_key: str = Query(..., description="MinIO object key (must start with 'projects/', 'golden-set/', or 'snapshots/')"),
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
