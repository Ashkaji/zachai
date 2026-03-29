"""
Unit tests for ffmpeg-worker main.py.

These tests mock MinIO and subprocess so no Docker environment is required.
Run: pytest test_main.py -v
"""
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set required env vars before importing the app
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECURE", "false")

from main import app, AUDIO_VIDEO_EXTENSIONS, TMP_BASE  # noqa: E402

client = TestClient(app)


# ─── GET /health ──────────────────────────────────────────────────────────────

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ─── POST /normalize ──────────────────────────────────────────────────────────

def _make_fake_wav(path: Path) -> None:
    """Write a minimal but real RIFF/WAVE header so ffprobe can read duration."""
    import struct
    # 44-byte WAV header for 0 samples, 16kHz mono PCM16
    num_samples = 0
    data_size = num_samples * 2
    path.write_bytes(
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )


@patch("main.minio_client")
@patch("main.subprocess.run")
def test_normalize_success(mock_subprocess, mock_minio):
    """Happy path: MinIO download OK, FFmpeg succeeds, upload OK."""
    job_dir_capture = {}

    def fake_fget(bucket, key, local_path):
        # Create a tiny input file at the requested path
        Path(local_path).write_bytes(b"\x00" * 16)

    def fake_subprocess(cmd, **kwargs):
        # Locate output.wav argument and write a fake WAV there
        output_idx = cmd.index("-y") + 1
        out_path = Path(cmd[output_idx])
        _make_fake_wav(out_path)
        job_dir_capture["dir"] = out_path.parent
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        result.stdout = "0.0"
        return result

    mock_minio.fget_object.side_effect = fake_fget
    mock_minio.fput_object.return_value = None
    mock_minio.stat_object.return_value = SimpleNamespace(size=16)
    mock_subprocess.side_effect = fake_subprocess

    response = client.post("/normalize", json={
        "input_bucket": "projects",
        "input_key": "test/sample.mp4",
        "output_bucket": "projects",
        "output_key": "test/sample_normalized.wav",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["output_key"] == "test/sample_normalized.wav"
    assert isinstance(body["duration_s"], float)

    mock_minio.fget_object.assert_called_once()
    mock_minio.fput_object.assert_called_once()


@patch("main.minio_client")
def test_normalize_minio_download_failure(mock_minio):
    """MinIO download failure → 500 with error message."""
    from minio.error import S3Error
    mock_minio.fget_object.side_effect = S3Error(
        "NoSuchKey", "The specified key does not exist.",
        "test/missing.mp4", "projects", "req-id", "host-id"
    )
    mock_minio.stat_object.return_value = SimpleNamespace(size=16)

    response = client.post("/normalize", json={
        "input_bucket": "projects",
        "input_key": "test/missing.mp4",
        "output_bucket": "projects",
        "output_key": "test/out.wav",
    })

    assert response.status_code == 500
    assert "error" in response.json()


@patch("main.minio_client")
@patch("main.subprocess.run")
def test_normalize_ffmpeg_failure(mock_subprocess, mock_minio):
    """FFmpeg non-zero exit → 422 with error details."""
    def fake_fget(bucket, key, local_path):
        Path(local_path).write_bytes(b"\x00" * 16)

    mock_minio.fget_object.side_effect = fake_fget
    mock_minio.stat_object.return_value = SimpleNamespace(size=16)

    bad_result = MagicMock()
    bad_result.returncode = 1
    bad_result.stderr = "Invalid data found when processing input"
    mock_subprocess.return_value = bad_result

    response = client.post("/normalize", json={
        "input_bucket": "projects",
        "input_key": "test/corrupt.mp4",
        "output_bucket": "projects",
        "output_key": "test/out.wav",
    })

    assert response.status_code == 422
    assert "FFmpeg failed" in response.json()["error"]


# ─── POST /batch ──────────────────────────────────────────────────────────────

@patch("main.minio_client")
@patch("main.subprocess.run")
def test_batch_success(mock_subprocess, mock_minio, tmp_path):
    """Batch with one audio file → processed=1, errors=[]."""
    audio_file = tmp_path / "interview.mp3"
    audio_file.write_bytes(b"\x00" * 32)

    def fake_subprocess(cmd, **kwargs):
        output_idx = cmd.index("-y") + 1
        out_path = Path(cmd[output_idx])
        _make_fake_wav(out_path)
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        result.stdout = "1.5"
        return result

    mock_subprocess.side_effect = fake_subprocess
    mock_minio.fput_object.return_value = None

    response = client.post("/batch", json={
        "local_dir": str(tmp_path),
        "output_bucket": "projects",
        "output_prefix": "normalized/",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 1
    assert body["errors"] == []
    mock_minio.fput_object.assert_called_once()


def test_batch_invalid_dir():
    """Non-existent local_dir → 400."""
    response = client.post("/batch", json={
        "local_dir": "/nonexistent/path/xyz",
        "output_bucket": "projects",
        "output_prefix": "out/",
    })
    assert response.status_code == 400
    assert "local_dir does not exist" in response.json()["error"]


@patch("main.minio_client")
@patch("main.subprocess.run")
def test_batch_skips_non_audio_files(mock_subprocess, mock_minio, tmp_path):
    """Files with unsupported extensions are ignored."""
    (tmp_path / "readme.txt").write_text("not audio")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "audio.wav").write_bytes(b"\x00" * 32)

    def fake_subprocess(cmd, **kwargs):
        output_idx = cmd.index("-y") + 1
        _make_fake_wav(Path(cmd[output_idx]))
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        result.stdout = "0.5"
        return result

    mock_subprocess.side_effect = fake_subprocess
    mock_minio.fput_object.return_value = None

    response = client.post("/batch", json={
        "local_dir": str(tmp_path),
        "output_bucket": "projects",
        "output_prefix": "out/",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 1  # only audio.wav


def test_audio_video_extensions_complete():
    """Verify all CMCI-required extensions are in the supported set."""
    required = {".mp4", ".mp3", ".aac", ".flac", ".wav", ".mkv", ".avi", ".m4a", ".ogg"}
    assert required.issubset(AUDIO_VIDEO_EXTENSIONS)


@patch("main.minio_client")
@patch("main.subprocess.run")
def test_normalize_temp_files_cleaned_up(mock_subprocess, mock_minio):
    """Temp job directory is removed after normalize, even on success."""
    created_job_dirs = []

    def fake_fget(bucket, key, local_path):
        Path(local_path).write_bytes(b"\x00" * 16)
        created_job_dirs.append(Path(local_path).parent)

    def fake_subprocess(cmd, **kwargs):
        output_idx = cmd.index("-y") + 1
        out_path = Path(cmd[output_idx])
        _make_fake_wav(out_path)
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        result.stdout = "0.0"
        return result

    mock_minio.fget_object.side_effect = fake_fget
    mock_minio.fput_object.return_value = None
    mock_minio.stat_object.return_value = SimpleNamespace(size=16)
    mock_subprocess.side_effect = fake_subprocess

    response = client.post("/normalize", json={
        "input_bucket": "projects",
        "input_key": "test/sample.wav",
        "output_bucket": "projects",
        "output_key": "test/out.wav",
    })

    assert response.status_code == 200
    for job_dir in created_job_dirs:
        assert not job_dir.exists(), f"Temp dir {job_dir} was not cleaned up"
