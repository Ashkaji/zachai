# Story 3.3: Model Registry & Hot-Reload OpenVINO

Status: done

<!-- Ultimate context: extends Story 3.2 worker with MinIO Model Registry pointer + 60s polling. Epic 4 deploys new weights to the registry; this story only consumes `models` bucket + `latest` pointer. -->

## Story

As the System,
I can detect when the active Whisper model version changes in the MinIO Model Registry (via the `latest` pointer object) and hot-reload OpenVINO in the running `openvino-worker` without restarting the container,
so that Frontend, Label Studio, and any internal caller that hits the same worker always use one coherent ASR model version (per PRD §4.6–§6.3).

---

## Acceptance Criteria

1. **Registry semantics (aligned with Story 1.1):** In bucket **`models`**, object key **`latest`** holds **UTF-8 text** whose content is the **active version prefix** (e.g. `whisper-cmci-v1.1/`). This is **not** a POSIX symlink — treat it exactly as [Source: `.bmad-outputs/implementation-artifacts/1-1-minio-bootstrap-bucket-structure.md` — Dev Notes / `models/latest`].
2. **Polling:** A background loop (asyncio **or** dedicated thread) runs with default interval **60 seconds** (configurable), reads **`models` / `latest`**, and compares to the **last successfully applied** pointer value **and** pointer **ETag** (if available). On **meaningful change**, the worker **syncs** the OpenVINO model directory from MinIO and **reloads** `WhisperPipeline` without process restart — matching [Source: `docs/prd.md` §4.6, §6.2–§6.3] and [Source: `docs/architecture.md` §1.C].
3. **Sync contract:** Given pointer content `P` (normalized: trim, strip surrounding quotes, ensure single trailing `/` optional but consistent), download **all objects** under prefix `P` inside bucket `models` into a fresh local directory under **`WHISPER_MODEL_CACHE_DIR`** (default `/var/cache/openvino-models`), verify the tree is non-empty and contains what `WhisperPipeline` expects (IR folder layout — same as Story 3.2 local path semantics). Only after a **complete** sync, **swap** the active engine **on disk path** used by `WhisperEngine`.
4. **Hot-reload safety:** Reload must **not** leave the worker without a working model: keep serving with the **previous** model until the new model loads successfully. If download or `WhisperPipeline` construction fails, **log** clearly, **increment** a visible error counter or status field, and **continue** with the previous model (no crash loop). Concurrent **`/transcribe`** requests must not observe torn reads — use a **lock** (or replace-only-after-success pattern) so inference always uses one consistent `WhisperEngine` instance.
5. **Startup path:** On container start: **(a)** If pointer object exists and resolves → prefer registry-backed model. **(b)** Else if `WHISPER_MODEL_PATH` points to an existing directory → use Story **3.2** bootstrap behavior (local path only) until a valid pointer appears. **(c)** If neither works → fail fast with actionable logs (ops must seed pointer + objects **or** mount `WHISPER_MODEL_PATH`).
6. **`GET /health`:** Extend JSON beyond Story 3.2 to include at minimum: `model_loaded` (bool), **`active_model_prefix`** (string or `null` if local-only bootstrap), **`registry_pointer_etag`** (string or `null` if unavailable), **`last_poll_utc`** (ISO8601 string or similar), **`last_reload_ok`** (bool). Maintain `{"status": "ok"}` when the worker is serving and the currently active model is loaded.
7. **Configuration:** New env vars documented in `src/.env.example` with safe defaults: `MODEL_REGISTRY_BUCKET` (default `models`), `MODEL_POINTER_KEY` (default `latest`), `MODEL_POLL_INTERVAL_SECONDS` (default `60`), `WHISPER_MODEL_CACHE_DIR` (default `/var/cache/openvino-models`). Existing `MINIO_*`, `WHISPER_MODEL_PATH`, `OV_DEVICE`, `INFER_TIMEOUT_SECONDS`, `ENVIRONMENT`, `OPENVINO_WORKER_TEST_MODE` (Story 3.2) remain supported; **production guard** on test mode unchanged.
8. **Errors / observability:** MinIO failures during poll (transient) should **not** kill the process; structured logs with bucket/key. For **`/transcribe`**, keep **`ERR_ASR_01`** mapping for inference failures per [Source: `docs/prd.md` §6.5]. Optional: include a **`model_generation`** or **`active_prefix`** field in logs on reload for ops correlation (not required in HTTP responses except `/health`).
9. **Compose:** Update `openvino-worker` service in `src/compose.yml` — pass new env vars; ensure **volume or writable layer** for `WHISPER_MODEL_CACHE_DIR` in dev docs (tmpfs acceptable for CI smoke; production may use named volume).
10. **Tests:** Extend `test_main.py` with **mocked** MinIO: (1) pointer change triggers logical “reload” path when `WhisperPipeline` is mocked, (2) failed sync does **not** clear `model_loaded`, (3) poll interval parsing validated. No real weights in CI.

---

## Tasks / Subtasks

- [x] **Task 1** — Define pointer normalization + MinIO prefix listing/download helper (streaming to disk, size limits consistent with Story 3.2 `MAX_FILE_SIZE` policy for **individual** objects; document total-tree budget or guard).
- [x] **Task 2** — Implement `ModelRegistryPoller` (or equivalent) + threading/async integration without blocking the event loop for bulk I/O (mirror `anyio.to_thread` usage from Story 3.2).
- [x] **Task 3** — Refactor `WhisperEngine` lifecycle to support **atomic swap**: build new engine on new path → verify → swap reference under lock → dispose old pipeline **safely** (avoid indefinite native handle leaks — document best effort).
- [x] **Task 4** — Wire startup resolution order (registry → fallback `WHISPER_MODEL_PATH`) and `/health` fields.
- [x] **Task 5** — Update `src/.env.example` and `src/compose.yml`; add short **smoke** note: `mc` put object to change `latest`, wait ≤60s, confirm `/health` shows new `active_model_prefix`.
- [x] **Task 6** — Unit tests + regression check Story 3.2 `/transcribe` contract unchanged.

### Review Findings (2026-03-29)

- [x] [Review][Patch] **Parse `MAX_MODEL_TREE_TOTAL_BYTES` safely** — `int(os.environ.get(...))` raises on import if the value is non-numeric; mirror `_parse_poll_interval_seconds`-style validation with clear error or fallback [`src/workers/openvino-worker/main.py` ~30–32]
- [x] [Review][Patch] **`/health` snapshot consistency** — `health()` reads `state.engine` and several `WorkerState` fields without `model_lock`; a poll could update fields between reads, producing a mixed old/new JSON payload [`src/workers/openvino-worker/main.py` ~578–590]
- [x] [Review][Patch] **Smoke script preflight** — `scripts/smoke_model_registry.py` uses dummy blobs; without `OPENVINO_WORKER_TEST_MODE=true`, `WhisperPipeline.load` will fail after sync. Add an explicit check (`docker compose exec openvino-worker printenv`) and abort with a one-line fix hint [`src/workers/openvino-worker/scripts/smoke_model_registry.py`]
- [x] [Review][Defer] **`retired_engines` growth** — every successful reload appends to `retired_engines` without eviction; long-lived processes with frequent pointer churn could accumulate bound native/Python objects [`src/workers/openvino-worker/main.py` ~497–499] — defer cap/TTL cleanup to a future hardening pass
- [x] [Review][Defer] **AC3 “IR layout” beyond non-empty tree** — sync only ensures `count > 0`; OpenVINO IR shape is validated indirectly when `WhisperPipeline` loads (reload failure keeps previous model). Optional explicit manifest check deferred [`src/workers/openvino-worker/main.py` ~276–315]
- [x] [Review][Defer] **Global `model_lock` serializes `/transcribe` and blocks swap** — correct for avoiding torn reads; long jobs delay hot-reload (accepted tradeoff; same family as Story 3.2 timeout/thread note) [`src/workers/openvino-worker/main.py` ~635–640]

---

## Dev Notes

### Scope boundaries

- **In scope:** Consumer of Model Registry pointer + **pull** model weights from MinIO + hot-reload in `openvino-worker`.
- **Out of scope:** Camunda / Flywheel **writing** new versions or updating `latest` (Epic **4.4**); FastAPI proxy to Whisper; Frontend/Label Studio changes — they already call whichever integrated API will eventually front this worker; this story ensures **one** worker fleet member reloads coherently (per-container).

### MinIO layout reminder

```
models/                          ← bucket
  latest                         ← object, body text: whisper-cmci-v1.1/
  whisper-cmci-v1.0/...          ← versioned prefixes (objects)
  whisper-cmci-v1.1/...
```

If your listing API returns only objects, implement prefix traversal consistently with `minio.list_objects(..., recursive=True)`.

---

## Technical Requirements & Architecture Guardrails

### Threading and asyncio

- Story 3.2 runs inference in `anyio.to_thread.run_sync`. Reload and heavy MinIO download must follow the same discipline: **never** block the event loop on large downloads or pipeline construction.

### Internal Shield

- Unchanged: worker remains **internal-only** — **no** host port mapping [Source: `docs/architecture.md` §5].

### Consistency with previous reviews (Story 3.2)

- Preserve **`stat_object`** / per-object size checks before download where applicable.
- Keep **`ffprobe` JSON** WAV validation on `/transcribe`.
- **`INFER_TIMEOUT_SECONDS`**: keep validated integer parsing at startup.
- **`OPENVINO_WORKER_TEST_MODE`**: never effective in production (`ENVIRONMENT=production`).

---

## Architecture Compliance

| Source | Requirement |
|--------|-------------|
| `docs/architecture.md` §1.C | Hot-reload via **60s** poll of `models/latest` (interpreted as bucket `models`, key `latest` per Story 1.1) |
| `docs/architecture.md` §5 | Worker stays off the public network |
| `docs/architecture.md` diagram | `OV -->|Poll models/latest| MinIO` |
| `docs/prd.md` §4.6, §6.2–§6.3 | Registry paths + polling interval + no container restart |
| Story `1-1-minio-bootstrap-bucket-structure.md` | Pointer object semantics for `latest` |

---

## Library / Framework Requirements

- **Reuse** Story 3.2 stack: `fastapi`, `uvicorn`, `minio`, `openvino_genai`, `anyio`, `pydantic`.
- **Pin** OpenVINO / GenAI in `requirements.txt` to **minor** (same standard as Story 3.2 code review).

---

## File Structure Requirements

```
src/
├── compose.yml                              ← MODIFY
├── .env.example                             ← MODIFY
└── workers/
    └── openvino-worker/
        ├── main.py                          ← MODIFY (registry + reload)
        ├── requirements.txt                 ← MODIFY if new deps (avoid unless needed)
        └── test_main.py                     ← MODIFY
```

Optional: small module split (e.g. `registry.py`) if `main.py` exceeds maintainability — **no** new top-level service containers.

---

## Testing Requirements

- **Unit:** Mock `Minio` client for pointer reads, etag, list + fget; mock `WhisperPipeline` constructor to simulate success/failure.
- **Integration (manual):** Docker Compose + `mc` to upload tiny dummy IR tree **or** document operator procedure using real weights — CI stays mock-only.

---

## Previous Story Intelligence (3.2)

Carry forward from `3-2-openvino-whisper-inference-preannotation.md` and implemented code:

- **Segment JSON contract** must remain **unchanged** (`start`, `end`, `text`, `confidence`).
- **Confidence extraction** and `CONFIDENCE_FALLBACK_FIXED` semantics — **do not** regress.
- **Review patches already applied:** `ffprobe` JSON, `stat_object` size guard, `INFER_TIMEOUT_SECONDS` validation, test-mode production guard.
- **Deferred:** timeout vs orphaned native thread — acceptable to document same limitation unless you introduce explicit cancellation.

**Explicit extension:** Engine lifecycle evolves from **load-once** to **load-or-swap** — adjust global `engine` management carefully for testability (avoid import-time side effects that prevent mocking reload).

---

## Git Intelligence Summary

Latest implementation work on **`7699282`** completed Story **3.2** (`openvino-worker` inference). Subsequent changes should extend the same service **in place** rather than introducing a second ASR container.

---

## Latest Technical Information

- OpenVINO GenAI **`WhisperPipeline`** is constructed from a **directory path**; hot-reload implies constructing a **new** pipeline instance and swapping references. Verify against current **`openvino_genai.WhisperPipeline`** docs for your pinned release — dispose old instances when practical to limit VRAM/RAM growth across many reload cycles.

---

## Project Context Reference

No `project-context.md` in-repo. Authoritative: **`docs/architecture.md`**, **`docs/prd.md`**, Story **`1-1`**, Story **`3-2`**, **`docs/api-mapping.md`** for downstream segment shape consumers.

---

## Traduction (français) — Résumé

- Le worker **`openvino-worker`** interroge MinIO (**bucket `models`**, objet **`latest`**) toutes les **60 s** (par défaut).
- Le corps de **`latest`** indique le **préfixe** de la version active (ex. `whisper-cmci-v1.1/`). Télécharger ce préfixe vers un cache local, recharger **`WhisperPipeline`** **sans** redémarrer le conteneur.
- En cas d’échec du rechargement, **conserver** l’ancien modèle opérationnel.
- Étendre **`GET /health`** pour l’observabilité (préfixe actif, ETag du pointeur, dernier poll).
- Mettre à jour **Compose** et **`.env.example`** pour les nouvelles variables.

---

## Dev Agent Record

### Agent Model Used

Cursor AI (GPT-5.2)

### Debug Log References

### Completion Notes List

- Implemented MinIO Model Registry consumer: `normalize_pointer_content`, `fetch_registry_pointer`, `sync_model_prefix_to_dir` (per-object `MAX_FILE_SIZE`, total `MAX_MODEL_TREE_TOTAL_BYTES`), bootstrap + `poll_once_sync` hot-swap guarded by `model_lock` so `/transcribe` never races a half-swap.
- Background poll via `asyncio.create_task(poll_loop)` + `anyio.to_thread.run_sync(poll_once_sync)`; extended `/health` with `active_model_prefix`, `registry_pointer_etag`, `last_poll_utc`, `last_reload_ok`, `reload_failures`, `model_source`.
- `WhisperEngine.retire_pipeline` best-effort after swap; prior engine kept referenced in `retired_engines` to limit native churn.
- **`OPENVINO_REGISTRY_SKIP_BOOTSTRAP`**: test-only env so pytest `TestClient` lifespan does not block on `minio:9000` DNS/connect during registry probe (documented in `.env.example`).
- `pytest` extended for pointer swap, failed sync, poll interval parsing, sync helper; all 15 tests pass.
- Optional **smoke** (operators): upload versioned IR under `models/<prefix>/…`, put object `models/latest` with UTF-8 body `<prefix>/`, wait `MODEL_POLL_INTERVAL_SECONDS`, `GET /health` on internal `8770` and verify `active_model_prefix` / ETag.
- **Post-review (2026-03-29):** `_parse_max_model_tree_total_bytes` for safe env parsing; `/health` builds response under `model_lock`; smoke script preflights `OPENVINO_WORKER_TEST_MODE` unless `--skip-test-mode-check`.

### File List

- `src/workers/openvino-worker/main.py`
- `src/workers/openvino-worker/test_main.py`
- `src/compose.yml`
- `src/.env.example`

## Change Log

- **2026-03-29:** Story 3.3 implementation — registry bootstrap, 60s poll hot-reload, health/compose/env/test updates.
- **2026-03-29:** Code review follow-up — MAX tree bytes parser, health snapshot lock, smoke test-mode preflight + `--skip-test-mode-check`.

---

## Story Completion Status

Code review patches applied (2026-03-29); status **`done`**.
