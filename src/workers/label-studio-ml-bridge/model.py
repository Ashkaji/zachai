"""
Label Studio ML Backend — bridge vers le worker OpenVINO + diarization ZachAI.

Suit le motif HumanSignal ``LabelStudioMLBase`` (voir label_studio_ml/default_configs).
En ``predict`` : télécharge l'audio de la tâche, normalise en WAV 16 kHz mono (FFmpeg),
dépose sur MinIO, appelle ``POST /transcribe`` (openvino-worker) et ``POST /diarize``
(diarization-worker) en parallèle, fusionne les résultats par chevauchement temporel,
et renvoie des pré-annotations Label Studio **par segment** (label speaker + textarea)
que l'expert réattribue aux vrais labels de la nature puis corrige le texte.

Si la diarization est désactivée ou échoue, repli sur le mode segments ASR seuls.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import uuid
from typing import Any, Dict, List, Optional

from label_studio_ml.model import LabelStudioMLBase
from label_studio_ml.response import ModelResponse
from minio import Minio
import httpx

logger = logging.getLogger(__name__)

DIARIZATION_ENABLED = os.environ.get("DIARIZATION_ENABLED", "true").lower() == "true"


def _parse_max_speaker_labels(raw: str | None) -> int:
    if raw is None or not str(raw).strip():
        return 10
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid MAX_SPEAKER_LABELS={raw!r}; expected integer >= 1"
        ) from exc
    if value < 1:
        raise RuntimeError("MAX_SPEAKER_LABELS must be >= 1")
    return value


MAX_SPEAKER_LABELS = _parse_max_speaker_labels(os.environ.get("MAX_SPEAKER_LABELS", "10"))


class ZachaiOpenVinoBridge(LabelStudioMLBase):
    """ML Backend qui délègue l'ASR + diarization aux microservices ZachAI."""

    def setup(self) -> None:
        self.set("model_version", os.environ.get("ZACHAI_ML_BACKEND_VERSION", "zachai-openvino-bridge-2"))
        endpoint = os.environ.get("MINIO_ENDPOINT", "")
        access = os.environ.get("MINIO_ACCESS_KEY", "")
        secret = os.environ.get("MINIO_SECRET_KEY", "")
        if not (endpoint and access and secret):
            raise ValueError("MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY are required")
        secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
        self._minio = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
        self._ov_url = os.environ.get("OPENVINO_WORKER_URL", "http://openvino-worker:8770").rstrip("/")
        self._diar_url = os.environ.get("DIARIZATION_WORKER_URL", "http://diarization-worker:8780").rstrip("/")
        self._diar_engine = os.environ.get("DIARIZATION_ENGINE", "")
        self._bucket = os.environ.get("ZACHAI_LS_MINIO_BUCKET", "projects")
        self._key_prefix = os.environ.get("ZACHAI_LS_MINIO_KEY_PREFIX", "label-studio-ml/").strip("/") + "/"
        self._ffmpeg = os.environ.get("ZACHAI_FFMPEG_BIN", "ffmpeg")

    # ── Tag resolution ──────────────────────────────────────────────────────

    def _resolve_label_audio_tags(self) -> tuple[str, str]:
        """Return (labels_from_name, audio_to_name) from the project label config."""
        try:
            if hasattr(self, "label_interface") and self.label_interface:
                from_name, to_name, _ = self.get_first_tag_occurence(
                    control_type="Labels",
                    object_type="Audio",
                )
                return from_name, to_name
        except Exception as exc:
            logger.debug("Could not infer Labels tag from label config: %s", exc)
        return (
            os.environ.get("ZACHAI_LS_LABEL_FROM_NAME", "label"),
            os.environ.get("ZACHAI_LS_LABEL_TO_NAME", "audio"),
        )

    def _resolve_text_audio_tags(self) -> tuple[str, str]:
        try:
            if hasattr(self, "label_interface") and self.label_interface:
                from_name, to_name, _ = self.get_first_tag_occurence(
                    control_type="TextArea",
                    object_type="Audio",
                )
                return from_name, to_name
        except Exception as exc:
            logger.debug("Could not infer TextArea tag from label config: %s", exc)
        return (
            os.environ.get("ZACHAI_LS_TRANSCRIPTION_FROM_NAME", "transcription"),
            os.environ.get("ZACHAI_LS_TRANSCRIPTION_TO_NAME", "audio"),
        )

    # ── Audio helpers ───────────────────────────────────────────────────────

    def _task_audio_url(self, task: Dict[str, Any]) -> str:
        data = task.get("data") or {}
        explicit = os.environ.get("ZACHAI_LS_AUDIO_DATA_KEY")
        if explicit and explicit in data:
            return str(data[explicit])
        for key in ("audio", "audiourl", "url"):
            if key in data and data[key]:
                val = data[key]
                if isinstance(val, str):
                    return val
        for val in data.values():
            if isinstance(val, str) and val.startswith(("http://", "https://", "/data/")):
                return val
        raise ValueError(
            "No audio URL in task['data']; set ZACHAI_LS_AUDIO_DATA_KEY or add an "
            "'audio' field per Label Studio task format."
        )

    def _normalize_wav(self, src_path: str) -> str:
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cmd = [
            self._ffmpeg, "-y", "-i", src_path,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            try:
                if os.path.isfile(out):
                    os.remove(out)
            except OSError:
                pass
            raise
        return out

    # ── Merge logic ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_label_speaker(raw: str) -> str:
        prefix = "SPEAKER_"
        if not isinstance(raw, str) or not raw.startswith(prefix):
            return "SPEAKER_00"
        try:
            idx = int(raw[len(prefix):])
        except ValueError:
            return "SPEAKER_00"
        if idx < 0:
            return "SPEAKER_00"
        if idx >= MAX_SPEAKER_LABELS:
            idx = MAX_SPEAKER_LABELS - 1
        return f"SPEAKER_{idx:02d}"

    @staticmethod
    def _merge_asr_diarization(
        asr_segments: list[dict[str, Any]],
        speaker_turns: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge ASR segments with speaker turns by timestamp overlap.

        For each speaker turn, collect overlapping ASR chunks and concatenate
        their text. Returns merged segments with speaker, text, start, end,
        and averaged confidence.
        """
        if not speaker_turns:
            return [
                {
                    "start": s["start"],
                    "end": s["end"],
                    "speaker": "SPEAKER_00",
                    "text": s.get("text", ""),
                    "confidence": s.get("confidence", 0.0),
                }
                for s in asr_segments
            ]

        merged: list[dict[str, Any]] = []
        for turn in speaker_turns:
            t_start, t_end = turn["start"], turn["end"]
            texts: list[str] = []
            confs: list[float] = []
            for seg in asr_segments:
                s_start, s_end = seg["start"], seg["end"]
                overlap_start = max(t_start, s_start)
                overlap_end = min(t_end, s_end)
                if overlap_start < overlap_end:
                    overlap_dur = overlap_end - overlap_start
                    seg_dur = max(s_end - s_start, 0.001)
                    ratio = overlap_dur / seg_dur
                    if ratio > 0.3:
                        texts.append(seg.get("text", "").strip())
                        confs.append(seg.get("confidence", 0.0))
                    elif ratio > 0.0 and seg.get("text", "").strip():
                        texts.append(seg.get("text", "").strip())
                        confs.append(seg.get("confidence", 0.0) * ratio)

            text = " ".join(t for t in texts if t)
            avg_conf = round(sum(confs) / len(confs), 4) if confs else 0.0

            merged.append(
                {
                    "start": t_start,
                    "end": t_end,
                    "speaker": ZachaiOpenVinoBridge._normalize_label_speaker(
                        str(turn.get("speaker", "SPEAKER_00"))
                    ),
                    "text": text,
                    "confidence": avg_conf,
                }
            )
        return merged

    # ── Main predict ────────────────────────────────────────────────────────

    def predict(
        self,
        tasks: List[Dict],
        context: Optional[Dict] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        if not tasks:
            return ModelResponse(predictions=[])
        label_from, audio_to = self._resolve_label_audio_tags()
        text_from, _ = self._resolve_text_audio_tags()
        version = str(self.get("model_version") or "0.0.1")
        predictions: list[dict[str, Any]] = []

        with httpx.Client(timeout=httpx.Timeout(900.0)) as client:
            for task in tasks:
                task_id = task.get("id", "0")
                audio_url = self._task_audio_url(task)
                local_audio = self.get_local_path(audio_url, task_id=task_id)
                wav_path: Optional[str] = None
                try:
                    wav_path = self._normalize_wav(local_audio)
                    key = f"{self._key_prefix}{task_id}-{uuid.uuid4().hex}.wav"
                    self._minio.fput_object(self._bucket, key, wav_path)

                    asr_segments: list[dict[str, Any]] = []
                    speaker_turns: list[dict[str, Any]] = []
                    r_asr = client.post(
                        f"{self._ov_url}/transcribe",
                        json={"input_bucket": self._bucket, "input_key": key},
                    )
                    if r_asr.status_code == 200:
                        asr_segments = r_asr.json().get("segments") or []
                    else:
                        logger.error("openvino-worker error %s: %s", r_asr.status_code, r_asr.text)

                    if DIARIZATION_ENABLED and asr_segments:
                        candidate_engines: list[str] = []
                        preferred = (self._diar_engine or "").strip()
                        if preferred:
                            candidate_engines.append(preferred)
                        for eng in ("pyannote", "sherpa-onnx"):
                            if eng not in candidate_engines:
                                candidate_engines.append(eng)

                        for eng in candidate_engines:
                            try:
                                diar_body: dict[str, Any] = {
                                    "input_bucket": self._bucket,
                                    "input_key": key,
                                    "engine": eng,
                                }
                                r_diar = client.post(
                                    f"{self._diar_url}/diarize",
                                    json=diar_body,
                                )
                                if r_diar.status_code == 200:
                                    speaker_turns = r_diar.json().get("speakers") or []
                                    if speaker_turns:
                                        logger.info(
                                            "diarization succeeded with engine=%s (%d turns)",
                                            eng,
                                            len(speaker_turns),
                                        )
                                        break
                                logger.warning(
                                    "diarization-worker engine=%s error %s: %s",
                                    eng,
                                    r_diar.status_code,
                                    r_diar.text[:500],
                                )
                            except Exception:
                                logger.warning(
                                    "diarization-worker engine=%s unreachable",
                                    eng,
                                    exc_info=True,
                                )

                    if not asr_segments:
                        continue

                    merged = self._merge_asr_diarization(asr_segments, speaker_turns)
                    result_items: list[dict[str, Any]] = []
                    total_conf = 0.0
                    for seg in merged:
                        seg_id = f"seg-{uuid.uuid4().hex[:8]}"
                        result_items.append(
                            {
                                "id": seg_id,
                                "type": "labels",
                                "from_name": label_from,
                                "to_name": audio_to,
                                "value": {
                                    "start": seg["start"],
                                    "end": seg["end"],
                                    "labels": [seg["speaker"]],
                                },
                            }
                        )
                        result_items.append(
                            {
                                "id": seg_id,
                                "type": "textarea",
                                "from_name": text_from,
                                "to_name": audio_to,
                                "value": {"text": [seg["text"]]},
                            }
                        )
                        total_conf += seg.get("confidence", 0.0)

                    avg_score = round(total_conf / len(merged), 4) if merged else 0.0
                    predictions.append(
                        {
                            "model_version": version,
                            "score": avg_score,
                            "result": result_items,
                        }
                    )
                except subprocess.CalledProcessError as exc:
                    logger.exception("ffmpeg normalization failed: %s", exc.stderr)
                except Exception:
                    logger.exception("predict() failed for task_id=%s", task_id)
                finally:
                    if wav_path and os.path.isfile(wav_path):
                        try:
                            os.remove(wav_path)
                        except OSError:
                            pass
        return ModelResponse(predictions=predictions)
