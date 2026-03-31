"""Tests légers (unittest). Sur Windows, ``label_studio_ml`` peut échouer (rq/fork) — skip auto."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("DIARIZATION_ENABLED", "false")

_IMPORT_ERROR: str | None = None
try:
    from model import ZachaiOpenVinoBridge
except Exception as exc:  # noqa: BLE001
    ZachaiOpenVinoBridge = None  # type: ignore[misc, assignment]
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


@unittest.skipIf(
    ZachaiOpenVinoBridge is None,
    f"Import model indisponible sur cette plateforme ({_IMPORT_ERROR}) — exécuter les tests dans l'image Docker Linux.",
)
class TestTaskAudioUrl(unittest.TestCase):
    def setUp(self) -> None:
        assert ZachaiOpenVinoBridge is not None
        self.bridge = ZachaiOpenVinoBridge.__new__(ZachaiOpenVinoBridge)

    def tearDown(self) -> None:
        os.environ.pop("ZACHAI_LS_AUDIO_DATA_KEY", None)

    def test_explicit_data_key(self) -> None:
        os.environ["ZACHAI_LS_AUDIO_DATA_KEY"] = "song"
        task = {"data": {"song": "https://example.com/a.mp3"}}
        self.assertEqual(self.bridge._task_audio_url(task), "https://example.com/a.mp3")

    def test_default_audio_key(self) -> None:
        task = {"data": {"audio": "/data/upload/1.wav"}}
        self.assertEqual(self.bridge._task_audio_url(task), "/data/upload/1.wav")


@unittest.skipIf(
    ZachaiOpenVinoBridge is None,
    f"Import model indisponible ({_IMPORT_ERROR})",
)
class TestPredictMocked(unittest.TestCase):
    def setUp(self) -> None:
        assert ZachaiOpenVinoBridge is not None
        self.bridge = ZachaiOpenVinoBridge.__new__(ZachaiOpenVinoBridge)
        self.bridge._minio = MagicMock()
        self.bridge._ov_url = "http://openvino:8770"
        self.bridge._diar_url = "http://diarization:8780"
        self.bridge._diar_engine = ""
        self.bridge._bucket = "projects"
        self.bridge._key_prefix = "ls/"
        self.bridge._ffmpeg = "ffmpeg"

    @patch("model.httpx.Client")
    @patch("model.subprocess.run")
    def test_predict_returns_per_segment_labels_and_textarea(self, mock_run, mock_client_cls) -> None:
        """predict() returns per-segment labels + textarea items when diarization is disabled."""
        self.bridge.get_local_path = MagicMock(return_value="/tmp/in.mp3")
        mock_run.return_value = MagicMock(returncode=0)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "segments": [
                {"text": "hello world", "start": 0.0, "end": 2.5, "confidence": 0.8},
                {"text": "goodbye", "start": 2.5, "end": 5.0, "confidence": 0.7},
            ]
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        self.bridge._resolve_label_audio_tags = MagicMock(return_value=("label", "audio"))
        self.bridge._resolve_text_audio_tags = MagicMock(return_value=("transcription", "audio"))
        self.bridge.get = MagicMock(side_effect=lambda k: "2.0" if k == "model_version" else None)

        out = self.bridge.predict(
            [{"id": 42, "data": {"audio": "http://ls/tasks/42/audio"}}],
            context=None,
        )
        self.assertEqual(len(out.predictions), 1)
        pred = out.predictions[0]
        result = pred["result"]
        labels_items = [r for r in result if r["type"] == "labels"]
        textarea_items = [r for r in result if r["type"] == "textarea"]
        self.assertEqual(len(labels_items), 2)
        self.assertEqual(len(textarea_items), 2)
        self.assertEqual(labels_items[0]["value"]["labels"], ["SPEAKER_00"])
        self.assertEqual(textarea_items[0]["value"]["text"], ["hello world"])
        self.assertEqual(labels_items[0]["id"], textarea_items[0]["id"])
        self.assertIn("score", pred)
        self.assertGreater(pred["score"], 0)

    @patch("model.httpx.Client")
    @patch("model.subprocess.run")
    def test_predict_supports_multiple_tasks(self, mock_run, mock_client_cls) -> None:
        self.bridge.get_local_path = MagicMock(return_value="/tmp/in.mp3")
        mock_run.return_value = MagicMock(returncode=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "segments": [{"text": "hello", "start": 0.0, "end": 1.0, "confidence": 0.8}]
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client
        self.bridge._resolve_label_audio_tags = MagicMock(return_value=("label", "audio"))
        self.bridge._resolve_text_audio_tags = MagicMock(return_value=("transcription", "audio"))
        self.bridge.get = MagicMock(side_effect=lambda k: "2.0" if k == "model_version" else None)

        out = self.bridge.predict(
            [
                {"id": 41, "data": {"audio": "http://ls/tasks/41/audio"}},
                {"id": 42, "data": {"audio": "http://ls/tasks/42/audio"}},
            ],
            context=None,
        )
        self.assertEqual(len(out.predictions), 2)


@unittest.skipIf(
    ZachaiOpenVinoBridge is None,
    f"Import model indisponible ({_IMPORT_ERROR})",
)
class TestMergeAsrDiarization(unittest.TestCase):
    def test_merge_with_speaker_turns(self) -> None:
        asr = [
            {"start": 0.0, "end": 2.0, "text": "hello", "confidence": 0.9},
            {"start": 2.0, "end": 4.0, "text": "world", "confidence": 0.8},
            {"start": 4.0, "end": 6.0, "text": "goodbye", "confidence": 0.7},
        ]
        speakers = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
        ]
        merged = ZachaiOpenVinoBridge._merge_asr_diarization(asr, speakers)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["speaker"], "SPEAKER_00")
        self.assertIn("hello", merged[0]["text"])
        self.assertEqual(merged[1]["speaker"], "SPEAKER_01")
        self.assertIn("goodbye", merged[1]["text"])

    def test_merge_without_speakers_falls_back(self) -> None:
        asr = [
            {"start": 0.0, "end": 2.0, "text": "hello", "confidence": 0.9},
        ]
        merged = ZachaiOpenVinoBridge._merge_asr_diarization(asr, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["speaker"], "SPEAKER_00")
        self.assertEqual(merged[0]["text"], "hello")

    def test_merge_caps_speaker_labels_to_schema(self) -> None:
        asr = [{"start": 0.0, "end": 2.0, "text": "hello", "confidence": 0.9}]
        speakers = [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_99"}]
        merged = ZachaiOpenVinoBridge._merge_asr_diarization(asr, speakers)
        self.assertEqual(merged[0]["speaker"], "SPEAKER_09")


class TestImportGuard(unittest.TestCase):
    """Sur CI Linux / dans l'image Docker, l'import doit réussir."""

    @unittest.skipUnless(sys.platform != "win32", "Windows host: rq may require fork context")
    def test_model_imports_on_unix(self) -> None:
        self.assertIsNotNone(ZachaiOpenVinoBridge, _IMPORT_ERROR)


if __name__ == "__main__":
    unittest.main()
