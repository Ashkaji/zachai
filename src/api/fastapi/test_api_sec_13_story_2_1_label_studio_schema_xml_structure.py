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

# ─── Story 2.1: label_studio_schema XML structure ────────────────────────────


def test_generate_xml_contains_expected_tags():
    """generate_label_studio_xml produces valid Label Studio XML with required elements."""
    labels = [
        make_mock_label(label_name="Orateur", label_color="#FF5733", is_speech=True),
        make_mock_label(label_name="Pause", label_color="#999999", is_speech=False),
    ]
    xml = main.generate_label_studio_xml(labels)
    assert "<View>" in xml
    assert "<AudioPlus" in xml
    assert 'name="audio"' in xml
    assert 'value="$audio"' in xml
    assert "<Labels" in xml
    assert 'toName="audio"' in xml
    assert "<Label" in xml
    assert "Orateur" in xml
    assert "Pause" in xml
    assert "<TextArea" in xml
    assert 'placeholder="Transcription..."' in xml
    assert 'perRegion="true"' in xml
    assert 'displayMode="region-list"' in xml
    assert "SPEAKER_00" in xml
    assert "SPEAKER_09" in xml


def test_generate_xml_speech_labels_first():
    """generate_label_studio_xml orders speech labels before non-speech labels."""
    labels = [
        make_mock_label(label_id=1, label_name="Pause", label_color="#999999", is_speech=False),
        make_mock_label(label_id=2, label_name="Orateur", label_color="#FF5733", is_speech=True),
        make_mock_label(label_id=3, label_name="Bruit", label_color="#555555", is_speech=False),
        make_mock_label(label_id=4, label_name="Traducteur", label_color="#33FF57", is_speech=True),
    ]
    xml = main.generate_label_studio_xml(labels)
    # Both speech labels must appear before both non-speech labels
    orateur_pos = xml.index("Orateur")
    traducteur_pos = xml.index("Traducteur")
    pause_pos = xml.index("Pause")
    bruit_pos = xml.index("Bruit")
    assert orateur_pos < pause_pos
    assert orateur_pos < bruit_pos
    assert traducteur_pos < pause_pos
    assert traducteur_pos < bruit_pos


