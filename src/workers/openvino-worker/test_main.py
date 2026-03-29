import os
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
os.environ.setdefault("WHISPER_MODEL_PATH", "/tmp/fake-whisper-model")
os.environ.setdefault("OV_DEVICE", "CPU")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("OPENVINO_WORKER_TEST_MODE", "true")
os.environ.setdefault("OPENVINO_REGISTRY_SKIP_BOOTSTRAP", "true")
os.environ.setdefault("MODEL_POLL_INTERVAL_SECONDS", "86400")
os.environ.setdefault("WHISPER_MODEL_CACHE_DIR", "/tmp/openvino-model-cache-test")

Path("/tmp/fake-whisper-model").mkdir(parents=True, exist_ok=True)

import main as openvino_main  # noqa: E402
from main import (  # noqa: E402
    app,
    fetch_registry_pointer,
    normalize_pointer_content,
    poll_once_sync,
    sync_model_prefix_to_dir,
    WhisperEngine,
    _parse_poll_interval_seconds,
)


class BytesIODup:
    """Minimal get_object response with read/close/release_conn."""

    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def close(self):
        pass

    def release_conn(self):
        pass


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


def test_health_includes_registry_fields(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_loaded"] is True
    assert "active_model_prefix" in data
    assert "registry_pointer_etag" in data
    assert "last_poll_utc" in data
    assert "last_reload_ok" in data
    assert "reload_failures" in data
    assert "model_source" in data


@patch.object(openvino_main, "minio_client")
@patch("main._validate_wav_format")
def test_transcribe_success(mock_validate, mock_minio, client):
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


@patch.object(openvino_main, "minio_client")
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


def test_parse_poll_interval_default_and_valid():
    assert _parse_poll_interval_seconds(None) == 60
    assert _parse_poll_interval_seconds("120") == 120


def test_parse_poll_interval_rejects_invalid():
    with pytest.raises(RuntimeError, match="MODEL_POLL_INTERVAL_SECONDS"):
        _parse_poll_interval_seconds("abc")
    with pytest.raises(RuntimeError, match="positive"):
        _parse_poll_interval_seconds("0")


def test_parse_max_model_tree_total_bytes_default_and_valid():
    from main import _DEFAULT_MAX_MODEL_TREE_TOTAL_BYTES, _parse_max_model_tree_total_bytes

    assert _parse_max_model_tree_total_bytes(None) == _DEFAULT_MAX_MODEL_TREE_TOTAL_BYTES
    assert _parse_max_model_tree_total_bytes("2048") == 2048


def test_parse_max_model_tree_total_bytes_rejects_invalid():
    from main import _parse_max_model_tree_total_bytes

    with pytest.raises(RuntimeError, match="MAX_MODEL_TREE_TOTAL_BYTES"):
        _parse_max_model_tree_total_bytes("abc")
    with pytest.raises(RuntimeError, match="positive"):
        _parse_max_model_tree_total_bytes("0")


def test_normalize_pointer_content():
    assert normalize_pointer_content("  whisper-cmci-v1.1 ") == "whisper-cmci-v1.1/"
    assert normalize_pointer_content('"whisper-cmci-v1.0/"') == "whisper-cmci-v1.0/"


def test_normalize_pointer_empty_raises():
    with pytest.raises(ValueError):
        normalize_pointer_content("  ")


def test_fetch_registry_pointer_missing():
    mock_client = MagicMock()
    mock_client.stat_object.side_effect = S3Error(
        None,
        "NoSuchKey",
        "no key",
        "latest",
        "r",
        "h",
        bucket_name="models",
        object_name="latest",
    )
    assert fetch_registry_pointer(mock_client, "models", "latest") is None


def test_poll_once_pointer_change_hot_swaps(tmp_path, monkeypatch):
    from main import WorkerState

    monkeypatch.setattr(openvino_main, "WHISPER_MODEL_CACHE_DIR", tmp_path)
    fresh = WorkerState()
    monkeypatch.setattr(openvino_main, "state", fresh)

    mock_client = MagicMock()

    def stat_side_effect(bucket, key):
        if key == "latest":
            return SimpleNamespace(size=20, etag="etag1")
        return SimpleNamespace(size=4, etag="ox")

    mock_client.stat_object.side_effect = stat_side_effect
    mock_client.get_object.return_value = BytesIODup(b"whisper-cmci-v1.1/")

    def list_objects(bucket, prefix, recursive=True):
        yield SimpleNamespace(
            object_name="whisper-cmci-v1.1/openvino_model.xml",
            is_dir=False,
        )

    mock_client.list_objects.side_effect = list_objects

    def fget(bucket, key, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"ir")

    mock_client.fget_object.side_effect = fget

    monkeypatch.setattr(openvino_main, "minio_client", mock_client)

    eng = WhisperEngine("/tmp/fake-whisper-model", "CPU")
    eng.model_loaded = True
    openvino_main.state.engine = eng
    openvino_main.state.last_applied_etag = "old"
    openvino_main.state.last_applied_body = "other/"

    poll_once_sync()

    assert openvino_main.state.engine is not eng
    assert openvino_main.state.engine.model_loaded is True
    assert openvino_main.state.active_model_prefix == "whisper-cmci-v1.1"
    assert openvino_main.state.last_reload_ok is True
    assert openvino_main.state.last_applied_etag == "etag1"


def test_poll_sync_failure_keeps_previous_engine(tmp_path, monkeypatch):
    from main import WorkerState

    monkeypatch.setattr(openvino_main, "WHISPER_MODEL_CACHE_DIR", tmp_path)
    monkeypatch.setattr(openvino_main, "state", WorkerState())

    mock_client = MagicMock()
    mock_client.stat_object.return_value = SimpleNamespace(size=20, etag="etag2")
    mock_client.get_object.return_value = BytesIODup(b"whisper-cmci-v9.9/")
    mock_client.list_objects.side_effect = RuntimeError("sync failed")
    monkeypatch.setattr(openvino_main, "minio_client", mock_client)

    eng = WhisperEngine("/tmp/fake-whisper-model", "CPU")
    eng.model_loaded = True
    openvino_main.state.engine = eng
    openvino_main.state.reload_failures = 0

    poll_once_sync()

    assert openvino_main.state.engine is eng
    assert openvino_main.state.reload_failures == 1
    assert openvino_main.state.last_reload_ok is False


def test_sync_model_prefix_to_dir_writes_files(tmp_path, monkeypatch):
    mock_client = MagicMock()

    def list_objects(bucket, prefix, recursive=True):
        yield SimpleNamespace(
            object_name="whisper-cmci-v1.0/a.bin",
            is_dir=False,
        )

    mock_client.list_objects.side_effect = list_objects
    mock_client.stat_object.return_value = SimpleNamespace(size=2, etag="e")

    def fget(bucket, key, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"ok")

    mock_client.fget_object.side_effect = fget

    dest = tmp_path / "out"
    sync_model_prefix_to_dir(mock_client, "models", "whisper-cmci-v1.0/", dest)
    assert (dest / "a.bin").read_bytes() == b"ok"
