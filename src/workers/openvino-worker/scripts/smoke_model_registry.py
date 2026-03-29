#!/usr/bin/env python3
"""
Smoke test: MinIO Model Registry + openvino-worker hot-reload (Story 3.3).

Prerequisites
-------------
- Compose project root is ``src/`` (this script runs ``docker compose -f compose.yml`` from there).
- Services up: at least ``minio``, ``minio-init``, and ``openvino-worker``.

For *dummy* objects (no real OpenVINO IR), enable test inference on the worker::

    OPENVINO_WORKER_TEST_MODE=true

and do **not** set ``OPENVINO_REGISTRY_SKIP_BOOTSTRAP`` (must be absent or false) so startup
and polls talk to MinIO.

Usage
-----
::

    cd src
    python ../workers/openvino-worker/scripts/smoke_model_registry.py

    python ../workers/openvino-worker/scripts/smoke_model_registry.py --wait-seconds 70 --no-restart

This script always uploads small dummy objects under the chosen prefixes. Unless you use
``--skip-test-mode-check``, the worker must have ``OPENVINO_WORKER_TEST_MODE=true`` or
``WhisperPipeline.load`` will fail on non-IR bytes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _compose_src_dir() -> Path:
    # scripts/smoke_model_registry.py -> openvino-worker/scripts -> workers -> src
    return Path(__file__).resolve().parents[3]


def _run_dc(
    cwd: Path,
    compose_args: list[str],
    *,
    stdin: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    argv = ["docker", "compose", "-f", "compose.yml", *compose_args]
    print("+", " ".join(argv), flush=True)
    use_text = stdin is None
    r = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        input=stdin,
        text=use_text,
    )

    def _emit(stream: bytes | str | None, err: bool) -> None:
        if not stream:
            return
        text = stream if isinstance(stream, str) else stream.decode(errors="replace")
        fd = sys.stderr if err else sys.stdout
        print(text, end="" if text.endswith("\n") else "\n", file=fd, flush=True)

    _emit(r.stdout, False)
    _emit(r.stderr, True)
    if check and r.returncode != 0:
        sys.exit(r.returncode)
    return r


def _mc_with_stdin(cwd: Path, mc_command_suffix: str, data: bytes) -> None:
    """Run mc after alias; mc_command_suffix is shell after '&& ', e.g. 'mc pipe z/models/k'"""
    script = (
        "mc alias set z http://127.0.0.1:9000 \"$MINIO_ROOT_USER\" \"$MINIO_ROOT_PASSWORD\" "
        f"&& {mc_command_suffix}"
    )
    _run_dc(cwd, ["exec", "-T", "minio", "sh", "-ec", script], stdin=data, check=True)


def _put_pointer(cwd: Path, body: str) -> None:
    body_norm = body if body.endswith("/") else body + "/"
    _mc_with_stdin(cwd, "mc pipe z/models/latest", body_norm.encode("utf-8"))


def _upload_object(cwd: Path, key: str, data: bytes) -> None:
    _mc_with_stdin(cwd, f"mc pipe z/{key}", data)


def _health_raw(cwd: Path) -> subprocess.CompletedProcess:
    return _run_dc(
        cwd,
        [
            "exec",
            "-T",
            "openvino-worker",
            "curl",
            "-sf",
            "http://127.0.0.1:8770/health",
        ],
        check=False,
    )


def _health(cwd: Path) -> dict:
    r = _health_raw(cwd)
    if r.returncode != 0:
        print("health curl failed", file=sys.stderr)
        sys.exit(1)
    assert isinstance(r.stdout, str)
    return json.loads(r.stdout)


def _require_test_mode_for_dummy_blobs(cwd: Path) -> None:
    r = _run_dc(
        cwd,
        ["exec", "-T", "openvino-worker", "printenv", "OPENVINO_WORKER_TEST_MODE"],
        check=False,
    )
    raw = (r.stdout or "").strip() if isinstance(r.stdout, str) else ""
    if raw.lower() == "true":
        return
    print(
        "This smoke uploads dummy .bin objects, not OpenVINO IR. "
        "The worker will fail to load WhisperPipeline unless test mode is on.\n"
        "Fix: set OPENVINO_WORKER_TEST_MODE=true for openvino-worker (see src/.env.example), "
        "or re-run with --skip-test-mode-check if your prefixes already hold a valid IR tree.\n"
        f"Current OPENVINO_WORKER_TEST_MODE={raw!r if raw else '(unset)'}",
        file=sys.stderr,
    )
    sys.exit(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=65.0,
        help="Wait after second pointer write before asserting (default: 65, above 60s poll).",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart openvino-worker after seeding v1 pointer.",
    )
    parser.add_argument(
        "--prefix-v1",
        default="smoke-v1",
        help="First version prefix (no bucket name; e.g. smoke-v1).",
    )
    parser.add_argument(
        "--prefix-v2",
        default="smoke-v2",
        help="Second version prefix after hot-reload.",
    )
    parser.add_argument(
        "--skip-test-mode-check",
        action="store_true",
        help="Do not require OPENVINO_WORKER_TEST_MODE=true (only if prefixes already contain valid OpenVINO IR).",
    )
    args = parser.parse_args()

    cwd = _compose_src_dir()
    compose_file = cwd / "compose.yml"
    if not compose_file.is_file():
        print(f"Expected compose.yml at {compose_file}", file=sys.stderr)
        sys.exit(2)

    p1 = args.prefix_v1.strip("/ ") + "/"
    p2 = args.prefix_v2.strip("/ ") + "/"

    ok = _run_dc(
        cwd,
        ["exec", "-T", "openvino-worker", "true"],
        check=False,
    )
    if ok.returncode != 0:
        print(
            "openvino-worker container not running or not healthy — "
            "`cd src && docker compose up -d minio minio-init openvino-worker`",
            file=sys.stderr,
        )
        sys.exit(2)

    if not args.skip_test_mode_check:
        _require_test_mode_for_dummy_blobs(cwd)

    b1 = f"smoke-bytes-{p1}-{time.time()}\n".encode()
    b2 = f"smoke-bytes-{p2}-{time.time()}\n".encode()

    print("--- Seeding MinIO objects under bucket models ---", flush=True)
    _upload_object(cwd, f"models/{p1}dummy.bin", b1)
    _upload_object(cwd, f"models/{p2}dummy.bin", b2)

    print(f"--- Pointer models/latest -> {p1!r} ---", flush=True)
    _put_pointer(cwd, p1)

    if not args.no_restart:
        print("--- docker compose restart openvino-worker ---", flush=True)
        _run_dc(cwd, ["restart", "openvino-worker"], check=True)
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            if _health_raw(cwd).returncode == 0:
                break
            time.sleep(1)
        else:
            print("openvino-worker health did not come up after restart", file=sys.stderr)
            sys.exit(1)

    h1 = _health(cwd)
    print("--- Health (v1) ---", flush=True)
    print(json.dumps(h1, indent=2))
    ap_expect = p1.rstrip("/")
    got1 = (h1.get("active_model_prefix") or "").replace("\\", "/")
    if ap_expect not in got1:
        print(
            f"FAIL: expected active_model_prefix containing {ap_expect!r}, got {got1!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"--- Pointer models/latest -> {p2!r} (expect poll + hot-reload) ---", flush=True)
    _put_pointer(cwd, p2)
    print(f"--- sleep {args.wait_seconds}s ---", flush=True)
    time.sleep(args.wait_seconds)

    h2 = _health(cwd)
    print("--- Health (v2) ---", flush=True)
    print(json.dumps(h2, indent=2))
    ap2_expect = p2.rstrip("/")
    got2 = (h2.get("active_model_prefix") or "").replace("\\", "/")
    if ap2_expect not in got2:
        print(
            f"FAIL: expected active_model_prefix containing {ap2_expect!r}, got {got2!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    if h2.get("last_reload_ok") is not True:
        print("FAIL: last_reload_ok should be true after successful reload", file=sys.stderr)
        sys.exit(1)

    print("--- Smoke OK ---", flush=True)


if __name__ == "__main__":
    main()
