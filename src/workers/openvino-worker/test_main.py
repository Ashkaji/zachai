import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from minio.error import S3Error

os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("WHISPER_MODEL_PATH", "/tmp/fake-whisper-model")
os.environ.setdefault("OV_DEVICE", "CPU")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("OPENVINO_WORKER_TEST_MODE", "true")

Path("/tmp/fake-whisper-model").mkdir(parents=True, exist_ok=True)

from main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _write_valid_wav(path: Path) -> None:
    import struct

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


def test_health_returns_model_loaded(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": True}


@patch("main._validate_wav_format")
@patch("main.minio_client")
def test_transcribe_success(mock_minio, mock_validate, client):
    def fake_fget(bucket, key, local_path):
        _write_valid_wav(Path(local_path))

    mock_validate.return_value = (True, "")
    mock_minio.stat_object.return_value = SimpleNamespace(size=1024)
    mock_minio.fget_object.side_effect = fake_fget

    response = client.post(
        "/transcribe",
        json={"input_bucket": "projects", "input_key": "normalized/sample.wav"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "segments" in body
    assert isinstance(body["segments"], list)
    assert set(body["segments"][0].keys()) == {"start", "end", "text", "confidence"}


@patch("main.minio_client")
def test_transcribe_missing_object(mock_minio, client):
    mock_minio.stat_object.side_effect = S3Error(
        None,
        "NoSuchKey",
        "The specified key does not exist.",
        "normalized/missing.wav",
        "req-id",
        "host-id",
        bucket_name="projects",
        object_name="normalized/missing.wav",
    )

    response = client.post(
        "/transcribe",
        json={"input_bucket": "projects", "input_key": "normalized/missing.wav"},
    )
    assert response.status_code == 404
    assert "error" in response.json()


def test_transcribe_invalid_body(client):
    response = client.post("/transcribe", json={"input_bucket": "projects"})
    assert response.status_code == 422


def test_extract_confidence_from_avg_logprob():
    from main import _extract_confidence

    seg = SimpleNamespace(confidence=None, avg_logprob=-0.5)
    c = _extract_confidence(seg)
    assert 0.0 < c <= 1.0


def test_parse_infer_timeout_seconds_default_and_valid():
    from main import MAX_INFER_TIMEOUT_SECONDS, _parse_infer_timeout_seconds

    assert _parse_infer_timeout_seconds(None) == 900
    assert _parse_infer_timeout_seconds("") == 900
    assert _parse_infer_timeout_seconds("  ") == 900
    assert _parse_infer_timeout_seconds("120") == 120
    assert _parse_infer_timeout_seconds(str(MAX_INFER_TIMEOUT_SECONDS)) == MAX_INFER_TIMEOUT_SECONDS


def test_parse_infer_timeout_seconds_rejects_invalid():
    from main import MAX_INFER_TIMEOUT_SECONDS, _parse_infer_timeout_seconds

    with pytest.raises(RuntimeError, match="Invalid INFER_TIMEOUT_SECONDS"):
        _parse_infer_timeout_seconds("abc")
    with pytest.raises(RuntimeError, match="must be positive"):
        _parse_infer_timeout_seconds("0")
    with pytest.raises(RuntimeError, match="must be <="):
        _parse_infer_timeout_seconds(str(MAX_INFER_TIMEOUT_SECONDS + 1))
