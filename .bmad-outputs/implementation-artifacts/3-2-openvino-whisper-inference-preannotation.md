# Story 3.2: OpenVINO/Whisper — Inférence & Pré-annotation

Status: done

<!-- Ultimate context: Epic 3 pipeline; depends on normalized 16 kHz mono PCM from Story 3.1. Story 3.3 adds MinIO `models/latest` polling hot-reload — out of scope here. -->

## Story

As the System,
I can run Whisper inference (OpenVINO) on a normalized audio object in MinIO and return timestamped segments as JSON,
so that the Frontend, Label Studio, and future FastAPI callbacks can attach a pré-annotation before any human edit.

---

## Acceptance Criteria

1. An `openvino-worker` service exists in `src/compose.yml`, **built from** `src/workers/openvino-worker/`, **internal only** (no host port mapping), `depends_on: minio: condition: service_healthy`, on `zachai-network`, `restart: unless-stopped`, with **cgroups-friendly** `deploy.resources` limits (CPU/RAM) consistent with `ffmpeg-worker` style.
2. The worker exposes `GET /health` returning JSON that includes **`{"status": "ok", "model_loaded": true}`** after weights are successfully loaded — used as the Docker healthcheck (via `curl` in `CMD-SHELL`, same pattern as `ffmpeg-worker`).
3. The worker exposes **`POST /transcribe`** accepting **`{"input_bucket": str, "input_key": str}`** (MinIO object pointing to **16 kHz mono PCM WAV**, as produced by `ffmpeg-worker`). It downloads the object to a temp directory, runs Whisper inference, and returns **`200 {"segments": [...]}`** where each segment is exactly **`{"start": float, "end": float, "text": str, "confidence": float}`** (seconds, UTF-8 text). Empty audio → `segments: []` with 200, not 500.
4. **Segment contract** matches `docs/prd.md` §6.3 and aligns with the shared transcription shape in §6.4 (`start`/`end`/`text`/`confidence`); do not invent parallel field names for the same concept.
5. **Scope boundary — Story 3.3:** do **not** implement MinIO **`models/latest` polling every 60s** or runtime hot-reload in this story. Load the active model **once at startup** from a configurable **local directory** inside the container (populated by image build, init script, or one-time copy from MinIO — see Dev Notes).
6. All MinIO credentials and model path configuration come from **environment variables** validated at startup (missing required vars → fail fast with clear logs). Never hardcode secrets.
7. Heavy inference must **not block the asyncio event loop** — use the same pattern as `ffmpeg-worker` (`anyio.to_thread.run_sync` or equivalent) for the synchronous OpenVINO/GenAI call.
8. **Robust errors:** invalid JSON body, missing MinIO object, FFmpeg/format failures, inference timeout, or OOM-prone inputs return **HTTP 4xx/5xx** with `{"error": "...", "code": "ERR_ASR_01"}` where appropriate (map ASR failures to `ERR_ASR_01` per `docs/prd.md` §6.5). Never crash the process silently.
9. **Tests:** `pytest` for `openvino-worker` with **mocked** MinIO and **mocked** pipeline/inference (no Docker, no real weights in CI). Cover happy path, missing object, and invalid body.
10. **Smoke procedure** documented in Dev Notes: `docker compose` exec on the internal network to `POST /transcribe` against a known WAV key in MinIO (developer-provided sample).

---

## Tasks / Subtasks

- [x] **Task 1** — Scaffold `src/workers/openvino-worker/` (`Dockerfile`, `requirements.txt`, `main.py`, `test_main.py`).
- [x] **Task 2** — Implement MinIO download + temp hygiene under `/tmp/openvino-worker/{uuid}/` with guaranteed cleanup (`try`/`finally` / `shutil.rmtree`).
- [x] **Task 3** — Implement OpenVINO GenAI Whisper inference wrapper producing the segment list; map model outputs to **`confidence`** with a documented rule (see Technical Requirements).
- [x] **Task 4** — Wire `GET /health` / `POST /transcribe`, startup env validation, timeouts, structured errors.
- [x] **Task 5** — Add service to `src/compose.yml` (uncomment/replace the `openvino` TODO block); internal port **8770** (avoids collision with `ffmpeg-worker` 8765).
- [x] **Task 6** — Extend `src/.env.example` with worker vars: `MINIO_*`, `WHISPER_MODEL_PATH` (or equivalent), optional `OV_DEVICE` (default `CPU`).
- [x] **Task 7** — Unit tests + local smoke notes.

---

### Review Findings (2026-03-29)

- [x] **[Review][Patch]** Confidence extraction treats `avg_logprob` like a 0–1 probability — negative log-probabilities clamp to `0.0`, so segment confidence is misleading unless real `confidence` exists on segments (`src/workers/openvino-worker/main.py`, `_extract_confidence`).
- [x] **[Review][Patch]** No `stat_object` / max-size guard before MinIO download — large objects can exhaust disk or memory vs Story 3.1 pattern and AC8 OOM-prone inputs (`src/workers/openvino-worker/main.py`, `/transcribe`).
- [x] **[Review][Patch]** Default stack: `.env.example` points `WHISPER_MODEL_PATH` at `/models/...` but `compose.yml` mounts no model volume and the image does not bake weights — container fails startup until operators add a bind mount or custom image (`src/compose.yml`, `src/.env.example`).
- [x] **[Review][Patch]** Story asks for pinned OpenVINO / GenAI minors; `requirements.txt` uses open lower bounds only (`src/workers/openvino-worker/requirements.txt`).
- [x] **[Review][Patch]** `OPENVINO_WORKER_TEST_MODE` skips loading a real pipeline with no production guard — accidental env in prod would return fake transcripts (`src/workers/openvino-worker/main.py`).
- [x] **[Review][Patch]** WAV validation parses `ffprobe` default text output line-by-line — brittle vs `-print_format json` for edge containers (`src/workers/openvino-worker/main.py`, `_validate_wav_format`).
- [x] **[Review][Defer]** Timeout via `anyio.fail_after` may return 504 while native inference continues on the thread pool — document or accept for v1 (`src/workers/openvino-worker/main.py`, `/transcribe`) — deferred, limitation of threaded native runtimes.

### Follow-up code review (2026-03-29, second pass)

- [x] **[Review][Patch]** Harden `INFER_TIMEOUT_SECONDS` parsing — `int(os.environ.get(...))` raises `ValueError` on bad input at import time; validate at startup with clear error (`src/workers/openvino-worker/main.py`).
- [x] **[Review][Defer]** TOCTOU between `stat_object` and `fget_object` if object is deleted mid-request — rare; accept for v1.

---

## Technical Requirements & Architecture Guardrails

### Input audio

- **Mandatory format:** 16 kHz, mono, PCM WAV — same contract as Story 3.1 output (`pcm_s16le`, `-ac 1`, `-ar 16000`). If the worker detects a mismatch (optional ffprobe check), return **400** with a clear error rather than opaque ASR failure.

### Output segments

- Timestamps in **seconds** (float), monotonic segments; **`text`** trimmed, no duplicate `start/end` keys.
- **`confidence`:** use the best signal the pipeline exposes (e.g. aggregated token log-probs normalized to \([0,1]\)). If the API does not expose token scores, document a **fallback** (e.g. segment-level placeholder with `0.75` **only** behind an explicit env `CONFIDENCE_FALLBACK_FIXED=true` for dev) — prefer real scores when available.

### Model loading (startup only)

- **`WHISPER_MODEL_PATH`:** filesystem path to an **OpenVINO Whisper model directory** compatible with `openvino_genai.WhisperPipeline(model_path, device)` (see Latest Tech below).
- **Optional bootstrap:** a documented one-liner using **`optimum-cli export openvino`** (or project-approved equivalent) to produce `whisper_ov` from a Hugging Face checkpoint; keep export **outside** the hot request path (build-time or admin-run script).
- **Do not** couple this story to Fine-tuning or Camunda; only inference.

### Internal Shield

Per `docs/architecture.md` §5 — **`openvino-worker` must not be reachable from the host**; only FastAPI/other internal services call it (FastAPI proxy integration can be a **later** story — this story delivers the worker contract only).

### Future FastAPI bridge (informational)

`docs/api-mapping.md` defines **`POST /v1/callback/transcription`** (body includes `audio_id` + `segments`). This story does **not** implement that endpoint; ensure **segment shape** matches so a future gateway story can forward without transformation.

---

## Architecture Compliance

| Source | Requirement |
|--------|-------------|
| `docs/architecture.md` §1.C | OpenVINO/Whisper ASR on 16 kHz mono PCM; dedicated compute container |
| `docs/architecture.md` §5 | Internal-only workers |
| `docs/architecture.md` §6 | Startup order: **`minio` healthy → `openvino-worker`** (after `ffmpeg-worker` in diagram; no direct dependency on `ffmpeg-worker` required) |
| `docs/prd.md` §4.3–4.4 | Pré-annotation Whisper universelle pour Frontend et Label Studio |
| `docs/prd.md` §6.3 | Input/output JSON schema |

---

## Library / Framework Requirements

- **Primary:** OpenVINO GenAI Whisper — **`openvino-genai`** / **`openvino`** Python packages pinned in `requirements.txt` (pin **minor** versions compatible with your base image).
- **HTTP:** `fastapi`, `uvicorn[standard]`, `pydantic` — mirror `ffmpeg-worker` baseline.
- **MinIO:** `minio>=7.2.0` — same patterns as `src/workers/ffmpeg-worker/main.py`.
- **Conversion (dev/build docs):** Hugging Face **Optimum** CLI to export OpenVINO IR — see [OpenVINO GenAI — Speech recognition](https://openvinotoolkit.github.io/openvino.genai/docs/use-cases/speech-recognition/) and [WhisperPipeline API](https://docs.openvino.ai/2026/api/genai_api/_autosummary/openvino_genai.WhisperPipeline.html).

---

## File Structure Requirements

```
src/
├── compose.yml                              ← MODIFY (add openvino-worker)
├── .env.example                             ← MODIFY
└── workers/
    └── openvino-worker/
        ├── Dockerfile
        ├── requirements.txt
        ├── main.py
        └── test_main.py
```

Follow **`ffmpeg-worker`** conventions: kebab-case service name `openvino-worker`, container_name `zachai-openvino-worker`, `build.context` relative to `src/`.

---

## Testing Requirements

- **Unit:** mock S3 client and mock `WhisperPipeline.generate` (or the thin wrapper), assert JSON schema and error codes.
- **Integration (optional local):** Docker compose + real tiny WAV + real model directory — not required for CI if too heavy; document manual smoke in Dev Notes.

---

## Previous Story Intelligence (3.1)

From `3-1-ffmpeg-worker-normalization-batch.md` and code review fixes — **carry forward:**

- Validate required env vars at **import/startup**; fail fast.
- Use **`anyio.to_thread.run_sync`** for blocking work (FFmpeg-style).
- Use **timeouts** on long-running native calls.
- Temp dirs under **`/tmp/<service>/uuid`**, cleanup on all paths.
- Catch **broad network exceptions** beyond `S3Error` when talking to MinIO.
- **Resource limits** in `compose.yml` for compute isolation.

**Contract with 3.1:** `/transcribe` expects the **normalized** object key (typically under `projects/.../normalized/...` per PRD §6.2). Do not re-run FFmpeg inside this worker unless explicitly adding a guard/detection step.

---

## Git Intelligence Summary

Recent commits emphasize **dashboard** and **audio upload** flows; compute workers follow the **`src/workers/<name>`** + **`compose.yml` Layer 2** pattern. Stay consistent with that layout (README’s `services/openvino` path is **aspirational** — **`workers/`** is the implemented pattern).

---

## Latest Technical Information

- OpenVINO **GenAI** documents Whisper at 16 kHz and provides **`WhisperPipeline`** for CPU/GPU without code forks between devices.
- Export path from Hugging Face checkpoints typically uses **`optimum-cli export openvino --model <id> ...`** then load the exported folder as `model_path`.
- Prefer **pinned** OpenVINO / GenAI versions in the Dockerfile to avoid silent API drift on `WhisperPipeline.generate`.

---

## Project Context Reference

No `project-context.md` found in-repo; treat **`docs/architecture.md`**, **`docs/prd.md`**, **`docs/api-mapping.md`**, and this story as authoritative for implementation.

---

## Dev Notes

### Default internal port

- **8770** — document in Dockerfile `EXPOSE 8770` and healthcheck `curl` URL.

### Relation to Story 3.3

- Story **3.3** adds **`models/latest` polling (60s)** and reload without container restart. This story may read a **static** `WHISPER_MODEL_PATH` that admins update when deploying a new image or volume mount — **no polling loop** here.

### UX

- No direct UI in this story; pré-annotation appears later in Frontend/Label Studio integrations. Output must still be **stable JSON** for those clients.

---

## Traduction (français) — Exigences résumées

- Nouveau service **`openvino-worker`** dans Docker Compose, **réseau interne uniquement**, dépend de MinIO.
- **`POST /transcribe`** : lit un WAV **16 kHz mono PCM** dans MinIO, renvoie `segments` avec `start`, `end`, `text`, `confidence`.
- **Pas de hot-reload MinIO** dans cette story (réservé à **3.3**).
- Charger le modèle **une fois au démarrage** depuis `WHISPER_MODEL_PATH`.
- Mêmes exigences de robustesse que le `ffmpeg-worker` (env, timeouts, thread pool, tests mockés).

---

## Dev Agent Record

### Agent Model Used

gpt-5.3-codex-low

### Debug Log References

- `python -m pytest -q` (in `src/workers/openvino-worker`) → **4 passed**
- `python -m pytest -q` (in `src/workers/ffmpeg-worker`) → **9 passed**

### Completion Notes List

- Follow-up review: `_parse_infer_timeout_seconds()` validates `INFER_TIMEOUT_SECONDS` at import (empty → 900, `ValueError` → clear `RuntimeError`, must be 1…7×86400); unit tests added.
- Post-review batch: `_extract_confidence` maps `avg_logprob` via `exp` after clamping to (-∞, 0]; `stat_object` + 1GiB cap before download; `_validate_wav_format` uses ffprobe JSON; `openvino` / `openvino-genai` pinned to `>=2025.0.0,<2025.1.0`; `OPENVINO_WORKER_TEST_MODE` disabled when `ENVIRONMENT` is `production`/`prod`; compose + `.env.example` document optional `WHISPER_MODEL_HOST_PATH` volume; job-dir errors return 500 without `ERR_ASR_01`.
- Implemented internal `openvino-worker` FastAPI service with startup model loading, `/health`, and `/transcribe`.
- Added strict env validation for `MINIO_*` and `WHISPER_MODEL_PATH`, with startup failure on missing config.
- Added MinIO download path, temporary workspace cleanup under `/tmp/openvino-worker/{uuid}`, and WAV format validation via `ffprobe`.
- Implemented non-blocking inference execution using `anyio.to_thread.run_sync` with timeout guard and structured ASR error mapping (`ERR_ASR_01` for inference failures).
- Added Docker image and Python dependencies for OpenVINO GenAI worker, and wired service in `src/compose.yml` as internal-only with healthcheck and resource limits.
- Extended `.env.example` with OpenVINO worker configuration (`WHISPER_MODEL_PATH`, `OV_DEVICE`, `INFER_TIMEOUT_SECONDS`) and export guidance.
- Added `pytest` unit coverage for health endpoint, transcribe success path, missing MinIO object, and invalid request body.
- Updated `ffmpeg-worker` unit tests to mock `stat_object` for compatibility with existing size-check behavior, keeping regression suite green.
- Local smoke notes (internal network):
  - `docker compose build openvino-worker && docker compose up -d openvino-worker`
  - `docker compose exec openvino-worker curl -s http://localhost:8770/health`
  - `docker compose exec openvino-worker curl -s -X POST http://localhost:8770/transcribe -H "Content-Type: application/json" -d '{"input_bucket":"projects","input_key":"test/sample_normalized.wav"}'`

### Change Log

- 2026-03-29: Implemented Story 3.2 OpenVINO/Whisper worker and marked story ready for code review.
- 2026-03-29: Code review (batch option 0) — applied confidence mapping for `avg_logprob`, MinIO size guard, ffprobe JSON validation, OpenVINO 2025.0.x pins, `ENVIRONMENT` + test-mode production guard, compose/.env model mount documentation; mkdir error no longer uses `ERR_ASR_01`.
- 2026-03-29: Second-pass review — hardened `INFER_TIMEOUT_SECONDS` parsing (`_parse_infer_timeout_seconds`, max 7 days).

### File List

- `src/workers/openvino-worker/main.py` (created)
- `src/workers/openvino-worker/test_main.py` (created)
- `src/workers/openvino-worker/Dockerfile` (created)
- `src/workers/openvino-worker/requirements.txt` (created)
- `src/compose.yml` (modified)
- `src/.env.example` (modified)
- `src/workers/ffmpeg-worker/test_main.py` (modified, regression test maintenance)
- `.bmad-outputs/implementation-artifacts/deferred-work.md` (deferred timeout note from review)
