"""Unit tests for diarization-worker (mocked engines)."""
from __future__ import annotations

import os
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from minio.error import S3Error

os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("DIARIZATION_TEST_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

import main as diar_main
from main import app, _normalize_speaker_ids, _parse_timeout_seconds


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _write_valid_wav(path: Path) -> None:
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


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "default_engine" in data
    assert "test_mode" in data


@patch.object(diar_main, "minio_client")
def test_diarize_success_test_mode(mock_minio, client):
    def fake_fget(bucket, key, local_path):
        _write_valid_wav(Path(local_path))

    mock_minio.stat_object.return_value = SimpleNamespace(size=1024)
    mock_minio.fget_object.side_effect = fake_fget

    response = client.post(
        "/diarize",
        json={"input_bucket": "projects", "input_key": "test/audio.wav"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "speakers" in body
    assert isinstance(body["speakers"], list)
    assert len(body["speakers"]) > 0
    assert "num_speakers" in body
    assert "engine" in body
    for turn in body["speakers"]:
        assert {"start", "end", "speaker"}.issubset(turn.keys())


@patch.object(diar_main, "minio_client")
def test_diarize_missing_object(mock_minio, client):
    mock_minio.stat_object.side_effect = S3Error(
        None, "NoSuchKey", "not found", "test/missing.wav",
        "req-id", "host-id", bucket_name="projects", object_name="test/missing.wav",
    )
    response = client.post(
        "/diarize",
        json={"input_bucket": "projects", "input_key": "test/missing.wav"},
    )
    assert response.status_code == 404


def test_normalize_speaker_ids():
    turns = [
        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_03"},
        {"start": 2.0, "end": 4.0, "speaker": "SPEAKER_07"},
        {"start": 4.0, "end": 6.0, "speaker": "SPEAKER_03"},
    ]
    result = _normalize_speaker_ids(turns)
    assert result[0]["speaker"] == "SPEAKER_00"
    assert result[1]["speaker"] == "SPEAKER_01"
    assert result[2]["speaker"] == "SPEAKER_00"


def test_normalize_speaker_ids_empty():
    assert _normalize_speaker_ids([]) == []


def test_normalize_speaker_ids_caps_to_schema_limit():
    turns = [{"start": float(i), "end": float(i + 1), "speaker": f"raw-{i}"} for i in range(12)]
    result = _normalize_speaker_ids(turns)
    # 10-label schema => overflow maps to SPEAKER_09
    assert result[9]["speaker"] == "SPEAKER_09"
    assert result[10]["speaker"] == "SPEAKER_09"
    assert result[11]["speaker"] == "SPEAKER_09"


def test_parse_timeout_seconds_validation():
    assert _parse_timeout_seconds("900") == 900
    with pytest.raises(RuntimeError):
        _parse_timeout_seconds("900s")
    with pytest.raises(RuntimeError):
        _parse_timeout_seconds("0")


def test_diarize_rejects_unknown_engine(client):
    response = client.post(
        "/diarize",
        json={"input_bucket": "projects", "input_key": "x.wav", "engine": "unknown"},
    )
    assert response.status_code == 400
