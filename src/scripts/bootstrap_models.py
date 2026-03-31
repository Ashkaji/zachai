#!/usr/bin/env python3
"""
ZachAI — Cross-platform model bootstrap: download from HuggingFace + seed MinIO registry.

Replaces the per-OS shell scripts (dev-up-openvino-labelstudio.ps1/.sh,
seed-openvino-model-registry.ps1/.sh) with a single Python entry point.

Usage (from zachai/src):
    python scripts/bootstrap_models.py                    # download + seed
    python scripts/bootstrap_models.py --skip-download    # seed only (model already on disk)
    python scripts/bootstrap_models.py --skip-seed        # download only (seed later)

Prerequisites:
    pip install huggingface_hub minio

Optional environment:
    HF_TOKEN / HUGGING_FACE_HUB_TOKEN — higher HF rate limits (recommended)
    MINIO_PRESIGNED_ENDPOINT — MinIO host reachable from this machine (default: localhost:9000)
    MINIO_ROOT_USER / MINIO_ROOT_PASSWORD — MinIO credentials (loaded from .env if present)
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ (no overwrite)."""
    if not path.is_file():
        return
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = pattern.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        for q in ('"', "'"):
            if val.startswith(q) and val.endswith(q) and len(val) >= 2:
                val = val[1:-1]
                break
        os.environ.setdefault(key, val)


def download_model(repo: str, dest: Path, http_timeout: int, retries: int, max_workers: int) -> None:
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(http_timeout)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Install huggingface_hub: pip install huggingface_hub", file=sys.stderr)
        raise SystemExit(1)

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        print(
            "Tip: set HF_TOKEN for higher rate limits — "
            "https://huggingface.co/docs/huggingface_hub/quick-start#authentication",
            file=sys.stderr,
            flush=True,
        )

    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {repo!r} -> {dest} (timeout={http_timeout}s, retries={retries}) ...", flush=True)

    last_err: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            snapshot_download(
                repo_id=repo,
                local_dir=str(dest),
                token=token,
                max_workers=max(1, max_workers),
            )
            print("Download complete.", flush=True)
            return
        except Exception as exc:
            last_err = exc
            print(f"Attempt {attempt}/{retries} failed: {exc}", file=sys.stderr, flush=True)
            if attempt < retries:
                delay = min(60, 5 * attempt)
                print(f"Retrying in {delay}s ...", file=sys.stderr, flush=True)
                time.sleep(delay)

    print("All download retries exhausted.", file=sys.stderr, flush=True)
    if last_err:
        raise SystemExit(1) from last_err
    raise SystemExit(1)


def seed_minio(model_dir: Path, prefix: str, endpoint: str, access_key: str, secret_key: str, secure: bool) -> None:
    """Upload model directory to MinIO models bucket and set the latest pointer."""
    try:
        from minio import Minio
    except ImportError:
        print("Install minio SDK: pip install minio", file=sys.stderr)
        raise SystemExit(1)

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    bucket = "models"
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        print(f"Created bucket '{bucket}'", flush=True)

    file_count = 0
    for file_path in model_dir.rglob("*"):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(model_dir).as_posix()
        object_name = f"{prefix}/{relative}"
        client.fput_object(bucket, object_name, str(file_path))
        file_count += 1
        print(f"  {object_name}", flush=True)

    if file_count == 0:
        print(f"WARNING: No files found in {model_dir} — registry will be empty.", file=sys.stderr, flush=True)
        return

    pointer_body = f"{prefix}/"
    data = pointer_body.encode("utf-8")
    client.put_object(bucket, "latest", io.BytesIO(data), len(data), content_type="text/plain")
    print(f"Seeded {file_count} files. models/latest -> {pointer_body}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download OpenVINO Whisper model and seed MinIO registry.",
    )
    parser.add_argument("--repo", default=os.environ.get("HF_WHISPER_OV_REPO", "OpenVINO/whisper-base-fp16-ov"),
                        help="HuggingFace repo (default: OpenVINO/whisper-base-fp16-ov)")
    parser.add_argument("--dest", type=Path, default=None,
                        help="Local model directory (default: <src>/models/whisper-base-ov)")
    parser.add_argument("--prefix", default=os.environ.get("MODEL_REGISTRY_PREFIX", "whisper-base-ov"),
                        help="MinIO object prefix (default: whisper-base-ov)")
    parser.add_argument("--http-timeout", type=int,
                        default=int(os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT", "3600")),
                        help="HF download timeout in seconds (default: 3600)")
    parser.add_argument("--retries", type=int,
                        default=int(os.environ.get("HF_DOWNLOAD_RETRIES", "5")),
                        help="HF download retries (default: 5)")
    parser.add_argument("--max-workers", type=int,
                        default=int(os.environ.get("HF_SNAPSHOT_MAX_WORKERS", "4")),
                        help="Parallel HF downloads (default: 4)")
    parser.add_argument("--skip-download", action="store_true", help="Skip HuggingFace download (seed only)")
    parser.add_argument("--skip-seed", action="store_true", help="Skip MinIO seeding (download only)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent

    load_dotenv(src_dir / ".env")

    prefix_slug = args.prefix.strip("/").split("/")[-1] or "whisper-base-ov"
    dest: Path = args.dest or (src_dir / "models" / prefix_slug)

    if not args.skip_download:
        download_model(args.repo, dest, args.http_timeout, args.retries, args.max_workers)

    if not args.skip_seed:
        if not dest.is_dir():
            print(f"Model directory not found: {dest}", file=sys.stderr)
            print("Run without --skip-download first, or set --dest to an existing model directory.", file=sys.stderr)
            return 1

        hp = os.environ.get("MINIO_PRESIGNED_ENDPOINT", "localhost:9000")
        if hp.startswith(("http://", "https://")):
            from urllib.parse import urlparse
            parsed = urlparse(hp)
            endpoint = parsed.netloc or hp
            secure = parsed.scheme == "https"
        else:
            endpoint = hp
            secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"

        access_key = os.environ.get("MINIO_ROOT_USER") or os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        secret_key = os.environ.get("MINIO_ROOT_PASSWORD") or os.environ.get("MINIO_SECRET_KEY", "minioadmin")

        print(f"Seeding MinIO registry at {endpoint} ...", flush=True)
        seed_minio(dest, args.prefix, endpoint, access_key, secret_key, secure)

    if args.skip_download and args.skip_seed:
        print("Both --skip-download and --skip-seed specified — nothing to do.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
