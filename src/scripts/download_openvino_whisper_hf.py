#!/usr/bin/env python3
"""
Télécharge un export Whisper OpenVINO depuis Hugging Face (aucun optimum-cli requis).

Référence: OpenVINO/whisper-base-fp16-ov (IR compatible stack openvino_genai du worker).

Usage (depuis zachai/src, avec MinIO optionnel pour amorcer le registre après coup):
    python scripts/download_openvino_whisper_hf.py
    python scripts/download_openvino_whisper_hf.py --repo OpenVINO/distil-whisper-large-v3-fp16-ov --dest models/distil-ov

Variables optionnelles:
    HF_TOKEN ou HUGGING_FACE_HUB_TOKEN — rate limits plus souples (recommandé)
    HF_HUB_DOWNLOAD_TIMEOUT — secondes (sinon --http-timeout ci-dessous; défaut 3600)

Note: huggingface_hub utilise HF_HUB_DOWNLOAD_TIMEOUT pour les flux HTTP ; la valeur par défaut
du paquet est 10s, ce qui provoque des ReadTimeout sur les gros binaires LFS si on ne l'augmente pas.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download OpenVINO Whisper from Hugging Face Hub.")
    parser.add_argument(
        "--repo",
        default=os.environ.get("HF_WHISPER_OV_REPO", "OpenVINO/whisper-base-fp16-ov"),
        help="Hub repo id (default: OpenVINO/whisper-base-fp16-ov)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Local directory (default: <src>/models/whisper-base-ov)",
    )
    parser.add_argument(
        "--http-timeout",
        type=int,
        default=int(os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT", "3600")),
        help="HF_HUB_DOWNLOAD_TIMEOUT in seconds (default: 3600; Hub default 10s is too low for LFS)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=int(os.environ.get("HF_DOWNLOAD_RETRIES", "5")),
        help="Retry snapshot_download on network timeout (default: 5)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=int(os.environ.get("HF_SNAPSHOT_MAX_WORKERS", "4")),
        help="Parallel Hub downloads (default: 4; lower if connection is unstable)",
    )
    args = parser.parse_args()

    # MUST be set before ``import huggingface_hub`` (constants read at import time).
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(args.http_timeout)

    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent
    if args.dest is not None:
        dest = args.dest
    else:
        hub_slug = args.repo.rsplit("/", 1)[-1]
        if hub_slug.endswith("-fp16-ov"):
            hub_slug = hub_slug[: -len("-fp16-ov")] + "-ov"
        dest = src_dir / "models" / hub_slug
    dest.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Install: pip install huggingface_hub", file=sys.stderr)
        return 1

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        print(
            "Tip: set HF_TOKEN for higher rate limits and fewer timeouts — "
            "https://huggingface.co/docs/huggingface_hub/quick-start#authentication",
            file=sys.stderr,
            flush=True,
        )

    print(
        f"Downloading {args.repo!r} -> {dest} "
        f"(HF_HUB_DOWNLOAD_TIMEOUT={args.http_timeout}s, retries={args.retries}) ...",
        flush=True,
    )
    last_err: BaseException | None = None
    for attempt in range(1, args.retries + 1):
        try:
            snapshot_download(
                repo_id=args.repo,
                local_dir=str(dest),
                token=token,
                max_workers=max(1, args.max_workers),
            )
            print(
                "Done. Next: seed MinIO with 'python scripts/bootstrap_models.py --skip-download'.",
                flush=True,
            )
            return 0
        except Exception as exc:
            last_err = exc
            print(
                f"Attempt {attempt}/{args.retries} failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            if attempt < args.retries:
                delay = min(60, 5 * attempt)
                print(f"Retrying in {delay}s ...", file=sys.stderr, flush=True)
                time.sleep(delay)

    print("All retries exhausted.", file=sys.stderr, flush=True)
    if last_err:
        raise SystemExit(1) from last_err
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
