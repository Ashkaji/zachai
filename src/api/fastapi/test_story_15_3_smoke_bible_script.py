"""
Story 15.3: unit tests for operator script `src/scripts/smoke_test_bible.py` (mocked HTTP).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "src" / "scripts" / "smoke_test_bible.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke_test_bible", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


smoke = _load_smoke_module()


def _ok_response(payload: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = payload
    return r


def test_smoke_test_bible_all_passes():
    """All four golden verses return 200 with matching snippets → True."""

    def fake_get(url, params=None, headers=None, timeout=None):
        ref = (params or {}).get("ref", "")
        tr = (params or {}).get("translation", "")
        snippets = {
            ("Jean 3:16", "LSG"): "Car Dieu a tant aimé le monde",
            ("Genèse 1:1", "LSG"): "Au commencement, Dieu créa",
            ("John 3:16", "KJV"): "For God so loved the world",
            ("Genesis 1:1", "KJV"): "In the beginning God created",
        }
        key = (ref, tr)
        text = snippets.get(key, "wrong")
        return _ok_response({"verses": [{"verse": 1, "text": text}]})

    with patch.object(smoke.requests, "get", side_effect=fake_get):
        assert smoke.smoke_test_bible("http://localhost:8000", "jwt") is True


def test_smoke_test_bible_404_fails():
    r404 = MagicMock()
    r404.status_code = 404

    with patch.object(smoke.requests, "get", return_value=r404):
        assert smoke.smoke_test_bible("http://localhost:8000", "jwt") is False


def test_smoke_test_bible_snippet_mismatch_fails():
    r = _ok_response({"verses": [{"verse": 16, "text": "Completely different text"}]})

    with patch.object(smoke.requests, "get", return_value=r):
        assert smoke.smoke_test_bible("http://localhost:8000", "jwt") is False


def test_smoke_test_bible_tolerates_verse_entries_without_text_key():
    """Malformed verse dicts should not raise; snippet match can still fail gracefully."""
    r = _ok_response({"verses": [{"verse": 1}, {"verse": 2, "text": "nope"}]})

    with patch.object(smoke.requests, "get", return_value=r):
        assert smoke.smoke_test_bible("http://localhost:8000", "jwt") is False
