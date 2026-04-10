import logging
import os
from pathlib import Path
import urllib.request
import io
import tarfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bootstrap-sherpa")

def _safe_extract_tar_bz2(data: bytes, target_dir: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as tf:
        base = target_dir.resolve()
        for member in tf.getmembers():
            member_path = (target_dir / member.name).resolve()
            if not str(member_path).startswith(str(base)):
                raise RuntimeError(f"Unsafe archive member path: {member.name!r}")
        tf.extractall(path=str(target_dir))

def bootstrap():
    cache_dir = Path(os.environ.get("SHERPA_MODEL_CACHE_DIR", "/var/cache/sherpa-models"))
    seg_model = cache_dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    emb_model = cache_dir / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"

    if seg_model.exists() and emb_model.exists():
        logger.info("Sherpa models already present in %s", cache_dir)
        return

    logger.info("Bootstrapping Sherpa models in %s...", cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    seg_url = os.environ.get(
        "SHERPA_SEG_MODEL_URL",
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
    )
    emb_url = os.environ.get(
        "SHERPA_EMB_MODEL_URL",
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recognition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
    )

    if not seg_model.exists():
        logger.info("Downloading segmentation model from %s", seg_url)
        with urllib.request.urlopen(seg_url, timeout=600) as resp:
            _safe_extract_tar_bz2(resp.read(), cache_dir)
        logger.info("Segmentation model ready.")

    if not emb_model.exists():
        logger.info("Downloading embedding model from %s", emb_url)
        with urllib.request.urlopen(emb_url, timeout=600) as resp:
            emb_model.write_bytes(resp.read())
        logger.info("Embedding model ready.")

if __name__ == "__main__":
    bootstrap()
