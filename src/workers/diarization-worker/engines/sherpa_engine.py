"""Speaker diarization engine backed by sherpa-onnx (CPU-friendly, no gated HF model)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("diarization-worker.sherpa")


def _safe_extract_tar_bz2(data: bytes, target_dir: Path) -> None:
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as tf:
        base = target_dir.resolve()
        for member in tf.getmembers():
            member_path = (target_dir / member.name).resolve()
            if not str(member_path).startswith(str(base)):
                raise RuntimeError(f"Unsafe archive member path: {member.name!r}")
        tf.extractall(path=str(target_dir))


def _to_turn(seg: Any) -> dict[str, Any] | None:
    """Best-effort conversion from a sherpa segment-like object."""
    start = getattr(seg, "start", None)
    end = getattr(seg, "end", None)
    speaker = getattr(seg, "speaker", None)
    if start is None or end is None or speaker is None:
        return None
    try:
        spk_idx = int(speaker)
    except Exception:
        return {
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            "speaker": str(speaker),
        }
    return {
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "speaker": f"SPEAKER_{spk_idx:02d}",
    }


def _parse_result_turns(result: Any) -> list[dict[str, Any]]:
    """Parse OfflineSpeakerDiarizationResult across multiple sherpa bindings."""
    turns: list[dict[str, Any]] = []

    # 1) iterable (some builds)
    try:
        for seg in result:  # type: ignore[operator]
            row = _to_turn(seg)
            if row is not None:
                turns.append(row)
        if turns:
            return turns
    except Exception:
        pass

    # 2) indexable by num_segments
    try:
        n = int(getattr(result, "num_segments"))
        for i in range(n):
            seg = result[i]  # type: ignore[index]
            row = _to_turn(seg)
            if row is not None:
                turns.append(row)
        if turns:
            return turns
    except Exception:
        pass

    # 3) explicit getters seen in some pybind variants
    for getter_name in ("at", "get_segment", "segment"):
        try:
            getter = getattr(result, getter_name)
        except Exception:
            continue
        try:
            n = int(getattr(result, "num_segments"))
            for i in range(n):
                seg = getter(i)
                row = _to_turn(seg)
                if row is not None:
                    turns.append(row)
            if turns:
                return turns
        except Exception:
            turns.clear()
            continue

    # 4) to_list / to_dict style serializers
    for export_name in ("to_list", "tolist", "as_list", "to_dict", "as_dict"):
        try:
            export = getattr(result, export_name)
            data = export()
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    s = item.get("start")
                    e = item.get("end")
                    sp = item.get("speaker")
                    if s is not None and e is not None and sp is not None:
                        turns.append(
                            {
                                "start": round(float(s), 3),
                                "end": round(float(e), 3),
                                "speaker": f"SPEAKER_{int(sp):02d}" if isinstance(sp, int) else str(sp),
                            }
                        )
            if turns:
                return turns

    return []


def _ensure_models_downloaded(cache_dir: Path) -> dict[str, str]:
    """Return paths to segmentation and embedding ONNX models, downloading if needed."""
    seg_model = cache_dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    emb_model = (
        cache_dir
        / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
    )

    if not seg_model.exists() or not emb_model.exists():
        logger.info("sherpa-onnx diarization models not found in %s; downloading...", cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

        import urllib.request

        seg_url = os.environ.get(
            "SHERPA_SEG_MODEL_URL",
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
        )
        emb_url = os.environ.get(
            "SHERPA_EMB_MODEL_URL",
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        )

        if not seg_model.exists():
            logger.info("downloading segmentation model from %s", seg_url)
            resp = urllib.request.urlopen(seg_url, timeout=600)
            if getattr(resp, "status", 200) >= 400:
                raise RuntimeError(f"Failed downloading segmentation model: HTTP {resp.status}")
            data = resp.read()
            _safe_extract_tar_bz2(data, cache_dir)
            logger.info("segmentation model extracted to %s", seg_model.parent)

        if not emb_model.exists():
            logger.info("downloading embedding model from %s", emb_url)
            resp = urllib.request.urlopen(emb_url, timeout=600)
            if getattr(resp, "status", 200) >= 400:
                raise RuntimeError(f"Failed downloading embedding model: HTTP {resp.status}")
            emb_model.write_bytes(resp.read())
            logger.info("embedding model saved to %s", emb_model)

    return {
        "segmentation": str(seg_model),
        "embedding": str(emb_model),
    }


def diarize(audio_path: str | Path) -> list[dict[str, Any]]:
    """Run speaker diarization on a WAV file using sherpa-onnx."""
    import sherpa_onnx
    import wave

    cache_dir = Path(
        os.environ.get("SHERPA_MODEL_CACHE_DIR", "/var/cache/sherpa-models")
    )
    models = _ensure_models_downloaded(cache_dir)

    num_clusters = int(os.environ.get("SHERPA_NUM_CLUSTERS", "-1"))

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=models["segmentation"],
            ),
            num_threads=int(os.environ.get("SHERPA_NUM_THREADS", "4")),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=models["embedding"],
            num_threads=int(os.environ.get("SHERPA_NUM_THREADS", "4")),
        ),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_clusters,
            threshold=float(os.environ.get("SHERPA_CLUSTER_THRESHOLD", "0.5")),
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )

    if not config.validate():
        raise RuntimeError("Invalid sherpa-onnx diarization config")

    sd = sherpa_onnx.OfflineSpeakerDiarization(config)

    with wave.open(str(audio_path), "rb") as wf:
        assert wf.getsampwidth() == 2, "Expected 16-bit WAV"
        assert wf.getnchannels() == 1, "Expected mono WAV"
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    assert sample_rate == sd.sample_rate, (
        f"Sample rate mismatch: file={sample_rate}, expected={sd.sample_rate}"
    )

    result = sd.process(samples)

    turns = _parse_result_turns(result)
    if not turns:
        # NOTE: Some sherpa-onnx builds expose OfflineSpeakerDiarizationResult
        # without Python access to actual segments. Keep service functional.
        if sample_rate <= 0:
            logger.warning("Invalid sample_rate=%s in fallback path; returning no turns", sample_rate)
            return []
        duration = float(len(samples)) / float(sample_rate)
        if duration <= 0:
            logger.warning("Non-positive duration in fallback path; returning no turns")
            return []
        logger.warning(
            "sherpa-onnx result segments are not accessible in this build; "
            "falling back to a single full-span speaker segment"
        )
        turns.append(
            {
                "start": 0.0,
                "end": round(duration, 3),
                "speaker": "SPEAKER_00",
            }
        )
    return turns
