"""Shared pytest fixtures for FastAPI gateway tests."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

import fastapi_test_app  # noqa: F401 — bootstrap env + app import side effects
from fastapi_test_app import main, _FakeNestedTransaction


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "api_health: presigned upload / health / auth slice",
    )
    config.addinivalue_line("markers", "api_natures: natures CRUD slice")
    config.addinivalue_line("markers", "api_projects: projects + audio register slice")
    config.addinivalue_line("markers", "api_assignments: assignment dashboard slice")
    config.addinivalue_line("markers", "api_golden: golden set / Camunda slice")
    config.addinivalue_line("markers", "api_transcription: transcription lifecycle slice")
    config.addinivalue_line("markers", "api_export: export / media slice")
    config.addinivalue_line("markers", "api_editor: editor ticket / snapshot / grammar slice")
    config.addinivalue_line("markers", "api_bible: bible engine + cache slice")


@pytest.fixture
def mock_db():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.expire = MagicMock()
    mock_session.begin_nested = MagicMock(return_value=_FakeNestedTransaction())

    async def override():
        yield mock_session

    main.app.dependency_overrides[main.get_db] = override
    yield mock_session
    main.app.dependency_overrides.pop(main.get_db, None)
