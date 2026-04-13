"""API gateway tests — auto-split from legacy test_main (see fastapi_test_app)."""
import os
import pytest
import httpx
import fakeredis.aioredis
from datetime import datetime, timezone
from typing import Annotated
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_test_app import (
    client,
    main,
    editor_ticket_mod,
    MANAGER_PAYLOAD,
    EXPERT_PAYLOAD,
    ADMIN_PAYLOAD,
    TRANSCRIPTEUR_PAYLOAD,
    MANAGER_OTHER_PAYLOAD,
    MOCK_JWKS,
    make_mock_label,
    make_mock_nature,
    make_mock_project,
    _make_mock_audio_with_assignment,
    _make_mock_snapshot,
    _FakeMinioObject,
    _FakeRedisBible,
)

# ─── Story 7.1: Export DOCX/TXT/SRT ───────────────────────────────────────────



def test_export_subtitle_srt_happy_path(mock_db):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="validated")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    snap_r = MagicMock()
    snap_r.scalar_one_or_none.return_value = _make_mock_snapshot()
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, snap_r])

    payload = b'{"segments":[{"start":0.0,"end":1.2,"text":"Bonjour"},{"start":1.2,"end":2.5,"text":"Le monde"}]}'
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "get_object", return_value=_FakeMinioObject(payload)):
        response = client.get(
            "/v1/export/subtitle/1?format=srt",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "attachment; filename=" in response.headers["content-disposition"]
    body = response.text
    assert "1\n00:00:00,000 --> 00:00:01,200\nBonjour" in body
    assert "2\n00:00:01,200 --> 00:00:02,500\nLe monde" in body


def test_export_transcript_txt_happy_path(mock_db):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="validated")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    snap_r = MagicMock()
    snap_r.scalar_one_or_none.return_value = _make_mock_snapshot()
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, snap_r])

    payload = b'{"text":"Bonjour\\nLe monde"}'
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "get_object", return_value=_FakeMinioObject(payload)):
        response = client.get(
            "/v1/export/transcript/1?format=txt",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Bonjour\nLe monde\n"


def test_export_transcript_docx_happy_path(mock_db):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="validated")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    snap_r = MagicMock()
    snap_r.scalar_one_or_none.return_value = _make_mock_snapshot()
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, snap_r])

    def _fake_get_object(bucket_name, object_name):
        if object_name.endswith(".json"):
            return _FakeMinioObject(b'{"text":"Texte DOCX"}')
        return _FakeMinioObject(b"FAKE_DOCX_BYTES")

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "get_object", side_effect=_fake_get_object):
        response = client.get(
            "/v1/export/transcript/1?format=docx",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.content == b"FAKE_DOCX_BYTES"


def test_export_transcript_invalid_format_422(mock_db):
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/export/transcript/1?format=pdf",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 422


def test_export_subtitle_non_validated_status_409(mock_db):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r])

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/export/subtitle/1?format=srt",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 409


def test_export_subtitle_invalid_segment_422(mock_db):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="validated")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    snap_r = MagicMock()
    snap_r.scalar_one_or_none.return_value = _make_mock_snapshot()
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, snap_r])

    payload = b'{"segments":[{"start":3.0,"end":2.0,"text":"bad"}]}'
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "get_object", return_value=_FakeMinioObject(payload)):
        response = client.get(
            "/v1/export/subtitle/1?format=srt",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 422


def test_export_subtitle_non_numeric_segment_422(mock_db):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="validated")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    snap_r = MagicMock()
    snap_r.scalar_one_or_none.return_value = _make_mock_snapshot()
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, snap_r])

    payload = b'{"segments":[{"start":"abc","end":2.0,"text":"bad"}]}'
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "get_object", return_value=_FakeMinioObject(payload)):
        response = client.get(
            "/v1/export/subtitle/1?format=srt",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 422


def test_export_transcript_expert_forbidden_403(mock_db):
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/export/transcript/1?format=txt",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


def test_export_transcript_docx_does_not_require_snapshot_json(mock_db):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="validated")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    snap_r = MagicMock()
    snap_r.scalar_one_or_none.return_value = _make_mock_snapshot()
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, snap_r])

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "get_object", return_value=_FakeMinioObject(b"ONLY_DOCX")) as get_obj:
        response = client.get(
            "/v1/export/transcript/1?format=docx",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.content == b"ONLY_DOCX"
    assert get_obj.call_count == 1


def test_whisper_transcribe_missing_api_key_401():
    response = client.post("/v1/whisper/transcribe", json={"audio_url": "https://example.com/audio.wav"})
    assert response.status_code == 401


def test_whisper_transcribe_invalid_api_key_403():
    response = client.post(
        "/v1/whisper/transcribe",
        headers={"Authorization": "Bearer wrong-key"},
        json={"audio_url": "https://example.com/audio.wav"},
    )
    assert response.status_code == 403


def test_whisper_transcribe_ssrf_block_422():
    response = client.post(
        "/v1/whisper/transcribe",
        headers={"Authorization": "Bearer test-whisper-open-api-key"},
        json={"audio_url": "http://127.0.0.1/audio.wav"},
    )
    assert response.status_code == 422


def test_whisper_transcribe_upstream_timeout_503():
    with patch.object(main, "_fetch_whisper_source_audio", new=AsyncMock(return_value=(b"WAV", "audio/wav"))), \
         patch.object(main, "_stage_whisper_audio_to_minio", return_value=("projects", "external-api/a.wav")), \
         patch.object(
             main,
             "_call_openvino_transcribe",
             new=AsyncMock(side_effect=HTTPException(status_code=503, detail={"error": "Transcription upstream timeout"})),
         ):
        response = client.post(
            "/v1/whisper/transcribe",
            headers={"Authorization": "Bearer test-whisper-open-api-key"},
            json={"audio_url": "https://example.com/audio.wav"},
        )
    assert response.status_code == 503


def test_whisper_transcribe_upstream_http_error_502():
    with patch.object(main, "_fetch_whisper_source_audio", new=AsyncMock(return_value=(b"WAV", "audio/wav"))), \
         patch.object(main, "_stage_whisper_audio_to_minio", return_value=("projects", "external-api/a.wav")), \
         patch.object(
             main,
             "_call_openvino_transcribe",
             new=AsyncMock(side_effect=HTTPException(status_code=502, detail={"error": "Transcription upstream error"})),
         ):
        response = client.post(
            "/v1/whisper/transcribe",
            headers={"Authorization": "Bearer test-whisper-open-api-key"},
            json={"audio_url": "https://example.com/audio.wav"},
        )
    assert response.status_code == 502


def test_whisper_transcribe_upstream_invalid_audio_422():
    with patch.object(main, "_fetch_whisper_source_audio", new=AsyncMock(return_value=(b"WAV", "audio/wav"))), \
         patch.object(main, "_stage_whisper_audio_to_minio", return_value=("projects", "external-api/a.wav")), \
         patch.object(
             main,
             "_call_openvino_transcribe",
             new=AsyncMock(side_effect=HTTPException(status_code=422, detail={"error": "Invalid audio payload for transcription"})),
         ):
        response = client.post(
            "/v1/whisper/transcribe",
            headers={"Authorization": "Bearer test-whisper-open-api-key"},
            json={"audio_url": "https://example.com/audio.wav"},
        )
    assert response.status_code == 422


def test_whisper_transcribe_success_shape_200():
    with patch.object(main, "_fetch_whisper_source_audio", new=AsyncMock(return_value=(b"WAV", "audio/wav"))), \
         patch.object(main, "_stage_whisper_audio_to_minio", return_value=("projects", "external-api/a.wav")), \
         patch.object(
             main,
             "_call_openvino_transcribe",
             new=AsyncMock(
                 return_value={
                     "segments": [{"start": 0.0, "end": 1.25, "text": "Bonjour", "confidence": 0.9}],
                     "model_version": "whisper-cmci-v1.0",
                 }
            ),
         ), \
         patch.object(main.internal_client, "remove_object") as rm_obj:
        response = client.post(
            "/v1/whisper/transcribe",
            headers={"Authorization": "Bearer test-whisper-open-api-key"},
            json={"audio_url": "https://example.com/audio.wav", "language": "fr"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "segments" in data and isinstance(data["segments"], list)
    assert data["segments"][0]["start"] == 0.0
    assert data["segments"][0]["end"] == 1.25
    assert data["segments"][0]["text"] == "Bonjour"
    assert "duration_s" in data
    assert data["language_detected"] == "fr"
    assert data["model_version"] == "whisper-cmci-v1.0"
    rm_obj.assert_called_once_with("projects", "external-api/a.wav")


def test_whisper_transcribe_get_method_not_allowed_405():
    response = client.get("/v1/whisper/transcribe")
    assert response.status_code == 405


def test_detect_citations_missing_api_key_401():
    response = client.post("/v1/nlp/detect-citations", json={"text": "John 3:16"})
    assert response.status_code == 401


def test_detect_citations_invalid_api_key_403():
    response = client.post(
        "/v1/nlp/detect-citations",
        headers={"Authorization": "Bearer wrong-key"},
        json={"text": "John 3:16"},
    )
    assert response.status_code == 403


def test_detect_citations_empty_text_422():
    response = client.post(
        "/v1/nlp/detect-citations",
        headers={"Authorization": "Bearer test-whisper-open-api-key"},
        json={"text": "   "},
    )
    assert response.status_code == 422


def test_detect_citations_success_with_offsets_200():
    text = "Famous verse: John 3:16 for many readers."
    response = client.post(
        "/v1/nlp/detect-citations",
        headers={"Authorization": "Bearer test-whisper-open-api-key"},
        json={"text": text},
    )
    assert response.status_code == 200
    data = response.json()
    assert "citations" in data and isinstance(data["citations"], list)
    assert data["citations"][0]["reference"] == "John 3:16"
    assert data["citations"][0]["start_char"] == text.index("John 3:16")
    assert data["citations"][0]["end_char"] == text.index("John 3:16") + len("John 3:16")


def test_detect_citations_no_match_returns_empty_200():
    response = client.post(
        "/v1/nlp/detect-citations",
        headers={"Authorization": "Bearer test-whisper-open-api-key"},
        json={"text": "This line has no scripture references."},
    )
    assert response.status_code == 200
    assert response.json() == {"citations": []}


def test_detect_citations_multiple_and_range_200():
    text = "Read Jn 3:16 and Romans 8:28-30 today."
    response = client.post(
        "/v1/nlp/detect-citations",
        headers={"Authorization": "Bearer test-whisper-open-api-key"},
        json={"text": text},
    )
    assert response.status_code == 200
    citations = response.json()["citations"]
    assert len(citations) == 2
    assert citations[0]["reference"] == "John 3:16"
    assert citations[1]["reference"] == "Romans 8:28-30"
    assert citations[0]["start_char"] < citations[1]["start_char"]


def test_detect_citations_dotted_abbreviation_200():
    text = "Reference: Jn. 3:16 in context."
    response = client.post(
        "/v1/nlp/detect-citations",
        headers={"Authorization": "Bearer test-whisper-open-api-key"},
        json={"text": text},
    )
    assert response.status_code == 200
    citations = response.json()["citations"]
    assert len(citations) == 1
    assert citations[0]["reference"] == "John 3:16"


def test_detect_citations_descending_range_filtered_200():
    text = "Invalid order John 3:16-14 should not be returned."
    response = client.post(
        "/v1/nlp/detect-citations",
        headers={"Authorization": "Bearer test-whisper-open-api-key"},
        json={"text": text},
    )
    assert response.status_code == 200
    assert response.json() == {"citations": []}


def test_detect_citations_unconfigured_key_503():
    with patch.object(main, "_WHISPER_OPEN_API_KEY", ""):
        response = client.post(
            "/v1/nlp/detect-citations",
            headers={"Authorization": "Bearer test-whisper-open-api-key"},
            json={"text": "John 3:16"},
        )
    assert response.status_code == 503


