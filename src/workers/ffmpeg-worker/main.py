import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ffmpeg-worker")

app = FastAPI(title="ffmpeg-worker")

AUDIO_VIDEO_EXTENSIONS = {".mp4", ".mp3", ".aac", ".flac", ".wav", ".mkv", ".avi", ".m4a", ".ogg"}
TMP_BASE = Path("/tmp/ffmpeg-worker")
MAX_FILE_SIZE = 1024 * 1024 * 1024

required_env = ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"]
missing = [env for env in required_env if env not in os.environ]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

minio_client = Minio(
    endpoint=os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
)

@app.on_event("startup")
async def startup_event():
    if TMP_BASE.exists():
        logger.info(f"Cleaning up {TMP_BASE}...")
        shutil.rmtree(TMP_BASE, ignore_errors=True)
    TMP_BASE.mkdir(parents=True, exist_ok=True)

class NormalizeRequest(BaseModel):
    input_bucket: str
    input_key: str
    output_bucket: str
    output_key: str

class BatchRequest(BaseModel):
    local_dir: str
    output_bucket: str
    output_prefix: str

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/normalize")
async def normalize(req: NormalizeRequest) -> Any:
    job_id = str(uuid.uuid4())
    job_dir = TMP_BASE / job_id
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to create job directory: {e}"})

    try:
        ext = Path(req.input_key).suffix or ".bin"
        input_path = job_dir / f"input{ext}"
        output_path = job_dir / "output.wav"

        try:
            stat = minio_client.stat_object(req.input_bucket, req.input_key)
            if stat.size > MAX_FILE_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"error": f"File too large: {stat.size} bytes"}
                )
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"MinIO stat failed: {e}"})

        try:
            await anyio.to_thread.run_sync(
                minio_client.fget_object, req.input_bucket, req.input_key, str(input_path)
            )
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"MinIO download failed: {e}"})

        if not input_path.exists():
            return JSONResponse(status_code=404, content={"error": "Downloaded file not found on disk"})

        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            "-y",
            str(output_path),
        ]
        
        try:
            result = await anyio.to_thread.run_sync(
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            )
        except subprocess.TimeoutExpired:
            return JSONResponse(status_code=504, content={"error": "FFmpeg processing timed out"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Subprocess error: {e}"})

        if result.returncode != 0:
            return JSONResponse(
                status_code=422,
                content={"error": f"FFmpeg failed: {result.stderr.strip()}"},
            )

        if not output_path.exists():
            return JSONResponse(status_code=422, content={"error": "FFmpeg produced no output file"})

        duration_s = await anyio.to_thread.run_sync(_get_wav_duration, output_path)

        try:
            await anyio.to_thread.run_sync(
                minio_client.fput_object,
                req.output_bucket,
                req.output_key,
                str(output_path),
                "audio/wav",
            )
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"MinIO upload failed: {e}"})

        return {"status": "ok", "output_key": req.output_key, "duration_s": duration_s}

    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

@app.post("/batch")
async def batch(req: BatchRequest) -> Any:
    local_dir = Path(req.local_dir)
    if not local_dir.exists() or not local_dir.is_dir():
        return JSONResponse(status_code=400, content={"error": "local_dir does not exist"})

    audio_files = [
        p for p in local_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_VIDEO_EXTENSIONS
    ]

    processed = 0
    errors: list[dict[str, str]] = []

    for file_path in audio_files:
        job_id = str(uuid.uuid4())
        job_dir = TMP_BASE / job_id
        try:
            job_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            errors.append({"file": str(file_path), "error": f"Failed to create job directory: {e}"})
            continue

        try:
            ext = file_path.suffix
            input_path = job_dir / f"input{ext}"
            output_path = job_dir / "output.wav"

            await anyio.to_thread.run_sync(shutil.copy2, file_path, input_path)

            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-acodec", "pcm_s16le",
                "-ac", "1",
                "-ar", "16000",
                "-y",
                str(output_path),
            ]
            
            try:
                result = await anyio.to_thread.run_sync(
                    lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                )
                if result.returncode != 0:
                    errors.append({"file": str(file_path), "error": f"FFmpeg failed: {result.stderr.strip()}"})
                    continue
            except subprocess.TimeoutExpired:
                errors.append({"file": str(file_path), "error": "FFmpeg timed out"})
                continue

            if not output_path.exists():
                errors.append({"file": str(file_path), "error": "FFmpeg produced no output file"})
                continue

            relative_stem = file_path.relative_to(local_dir).with_suffix("").as_posix()
            output_key = f"{req.output_prefix}{relative_stem}{file_path.suffix}.wav"

            try:
                await anyio.to_thread.run_sync(
                    minio_client.fput_object,
                    req.output_bucket,
                    output_key,
                    str(output_path),
                    "audio/wav",
                )
            except Exception as e:
                errors.append({"file": str(file_path), "error": f"MinIO upload failed: {e}"})
                continue

            processed += 1

        except Exception as e:
            errors.append({"file": str(file_path), "error": str(e)})

        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    return {"processed": processed, "errors": errors}

def _get_wav_duration(wav_path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Failed to get duration for {wav_path}: {e}")
        return 0.0
