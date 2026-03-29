## Deferred from: code review of 1-2-keycloak-multi-roles.md (2026-03-28)

- **Overprivileged Database Access (Shared Superuser)**: Keycloak and the future ZachAI service share a single superuser (`POSTGRES_USER`). This violates the principle of least privilege; each service should ideally have its own user and scoped permissions. [src/compose.yml:101]
- **Missing container resource constraints (limits/reservations)**: No `limits` or `reservations` are defined for the containers. Keycloak (JVM) is prone to memory spikes and could potentially starve the host or other services. [src/compose.yml:97]

## Deferred from: code review of 2-1-crud-natures-label-schemas.md (2026-03-28)

- **N+1 query pattern in list view**: `list_natures` calculates `label_count` by iterating over nature objects and their label collections. This should be optimized with a SQL `count()` join.
- **Repeated role authorization logic across endpoints**: Role checks are duplicated in every route; should be refactored into a reusable FastAPI dependency.
- **Brittle database initialization (Alembic missing)**: Relying on `create_all` is insufficient for production schema evolution.

## Deferred from: code review of 2-3-audio-upload-ffmpeg-normalization.md (2026-03-29)

- **Legacy presigned PUT vs project-scoped upload** — `POST /v1/upload/request-put` remains Manager-only with string `project_id`; Story 2.3 routes allow Admin and int `project_id`. Defer alignment/deprecation to a future cleanup story.

## Deferred from: code review of 2-2-project-creation-label-studio-provisioning.md (2026-03-29)

- **Project ID Timing in Camunda**: Project may not be durable when Camunda starts process — distributed systems timing edge case. Acceptable eventual consistency model per design spec.
- **KEYCLOAK JWKS Fetch Failure**: Startup doesn't fail if JWKS unreachable — pre-existing from Story 1.3; outside scope of Story 2.2.
- **Concurrency: Camunda Updates Committed Project**: Project visible with null process_instance_id between commit and update — by design; eventual consistency model is explicit.
- **Status Transition State Machine**: No intermediate "PROVISIONING" state between DRAFT and ACTIVE — design decision; simplistic but acceptable for current epic.
- **Worker DB Connection Pooling**: Per-call asyncpg.connect() instead of connection pool — performance optimization; not a blocker.

## Deferred from: code review of 2-4-assignment-dashboard.md (2026-03-29)

- **Cross-manager project status mutation remains possible on legacy `PUT /v1/projects/{project_id}/status`**: endpoint still permits any Manager/Admin without owner check. This predates Story 2.4 assignment endpoints and should be handled in a dedicated authorization-hardening change.
- **Owner-check error semantics for missing JWT `sub`**: helper currently reports 403 “Not the project owner” rather than a 401/token-shape error when `sub` is absent. Existing behavior predates this review and can be standardized in auth cleanup.

## Deferred from: code review of 3-2-openvino-whisper-inference-preannotation.md (2026-03-29)

- **Inference timeout vs threaded native run**: `anyio.fail_after` can return HTTP 504 while the blocking `WhisperPipeline.generate` call continues on the worker thread until completion — acceptable v1 limitation unless process pool or cancelable API is introduced (`src/workers/openvino-worker/main.py`).
- **MinIO stat then download (TOCTOU)**: object can disappear after `stat_object` and before `fget_object`; client may see 500 instead of 404 — rare operational race (`src/workers/openvino-worker/main.py`).

## Deferred from: code review of 3-3-model-registry-hot-reload.md (2026-03-29)

- **`retired_engines` list growth**: successful hot-reloads append retired `WhisperEngine` instances without eviction; consider a maxlen or periodic cleanup after N reloads to cap memory/native handles in very long-lived workers (`src/workers/openvino-worker/main.py`).
- **IR layout validation**: story AC3 mentions verifying OpenVINO IR layout; implementation validates via non-empty sync + `WhisperPipeline.load()` on reload failure path — optional explicit file manifest check deferred.
- **`model_lock` scope**: single lock serializes all inference and blocks swap during long `transcribe` calls — intentional for safety; document operational expectation that reload may lag behind pointer updates under heavy ASR load (`src/workers/openvino-worker/main.py`).

## Deferred from: code review of 4-1-golden-set-expert-loop-label-studio-webhook.md (2026-03-29)

- **Auth verification as imperative calls, not FastAPI `Depends()`**: `verify_label_studio_webhook_secret` and `verify_golden_set_internal_secret` are called manually inside route handlers rather than injected via `Depends()`. Pre-existing pattern across the codebase.
- **No request body size limit on webhook endpoint**: `/v1/callback/expert-validation` calls `await request.json()` with no body size restriction. FastAPI/Starlette defaults apply; operational hardening for a future story.
- **Test env vars set globally via `os.environ.setdefault`**: Test secrets are set at module level, polluting process environment. Same pattern used by all prior stories.
- **`source`/`weight` not validated at DB level**: DB columns are plain `String`; Pydantic validators are the only gate. Consistent with all other ORM models in the project.

## Deferred from: code review of 4-2-golden-set-user-loop-frontend-corrections (2026-03-29)

- **W1 — Expert webhook serializes N DB/MinIO round-trips**: `post_expert_validation_callback` calls `persist_golden_set_entry` in a serial loop; one annotation with many segments creates N full round-trips in a single HTTP request. Story 4.1 design; optimize with batch insert in future.
- **W2 — No Alembic/migration tool**: Codebase relies on `Base.metadata.create_all` which won't add columns/indexes to existing tables. Pre-existing architectural choice.
- **W3 — No rate limiting on correction endpoint**: `POST /v1/golden-set/frontend-correction` has no throttle or per-user rate limit. Infrastructure concern for future hardening.
- **W4 — Redundant guard in `normalize_expert_validation_payload`**: `golden_set.py:208` — `if annotation is None and isinstance(body.get("annotation"), dict) is False` second clause is tautologically true when first is true. Story 4.1 helper code.
- **W5 — LS project verification silently passes for unknown project**: When `label_studio_project_id_for_verify` is set but no Project row matches, verification passes silently. Story 4.1 code path.
- **W6 — Frontend sequential correction submission**: `submitCorrections` fires N sequential `fetch` calls per debounce cycle; performance optimization for future story.
- **W7 — `GOLDEN_SET_THRESHOLD` accepts 0 or negative**: threshold env var is parsed but never consumed until Story 4.3; validate range then.
- **W8 — `api-mapping.md` describes Camunda trigger but code doesn't fire it**: pre-existing docs text; Camunda trigger is a Story 4.3 concern.

## Deferred from: code review of 4-3-lora-finetuning-auto-trigger-camunda.md (2026-03-29)

- **Compose builds for Postgres/Keycloak (`src/docker/*`)**: Changes are outside story 4.3 file list but address Docker Desktop Windows bind mounts; ensure CI or README covers building from `src/` context when using compose.

## Deferred from: code review of story 4-4-lora-pipeline-dataset-training-validation-deploy.md (2026-03-29)

- **`model-ready` idempotency vs counter commit boundary**: If the API crashes after inserting `ModelReadyIdempotency` but before committing `GoldenSetCounter` updates, a retry can return `idempotent: true` while the counter remains non-zero — rare; reconcile manually or tighten transactional ordering in a follow-up.
