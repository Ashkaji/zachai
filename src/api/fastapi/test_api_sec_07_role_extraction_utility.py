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

# ─── Role extraction utility ─────────────────────────────────────────────────


def test_get_roles_from_payload():
    """get_roles returns the list of realm_access.roles from JWT payload."""
    payload = {"realm_access": {"roles": ["Manager", "offline_access"]}}
    roles = main.get_roles(payload)
    assert "Manager" in roles


def test_get_roles_empty_payload():
    """get_roles returns empty list when realm_access missing."""
    roles = main.get_roles({})
    assert roles == []


