## Deferred from: code review of 16-1-keycloak-admin-client-and-service-account.md (2026-04-13)

- **Concurrent admin token fetch**: Multiple concurrent `get_admin_token()` calls on a cold cache can each POST to Keycloak until the first response fills `_admin_token_cache`; acceptable for v1 (AC5); revisit with `asyncio.Lock` if this becomes hot or rate-limited. [`src/api/fastapi/keycloak_admin.py`]
- **Realm import / service-account role mappings**: Validate on a fresh Keycloak 26 compose import that `service-account-zachai-admin-cli` receives `realm-management` roles as intended; realm JSON can be version-sensitive. [`src/config/realms/zachai-realm.json`]

## Deferred from: code review of 15-2-bible-extract-to-zachai-json.md (2026-04-13)

- **Golden verse smoke strictness (AC #4)**: Operator deferred policy (option 0). Decide later: `--translation KJV|LSG` with strict goldens, narrow AC wording, or another rule. [`src/scripts/validate_bible_json.py`]
- **Regex extraction of `_BIBLE_BOOK_ALIASES`**: `validate_bible_json.py` parses `main.py` with a regex; refactoring the dict literal in `main.py` could break validation until the parser is updated. [`src/scripts/validate_bible_json.py`]

## Deferred from: code review of 12-3-restauration-securisee-verrouillage-websocket.md (2026-04-12)

- **Remote restore failure visibility**: After a failed restore, `finally` still publishes `document_unlocked`; collaborators who saw `document_locked` may think the restore completed. Only the initiating client gets the HTTP error. Optional follow-up: broadcast a failure stateless message (e.g. `zachai:document_restore_failed`). [`src/api/fastapi/main.py`]

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

## Deferred from: code review of 5-2-secure-wss-handshake-ticket-redis.md (2026-03-30)

- **`consume_wss_ticket` JSON parse failures**: If Redis returns non-JSON bytes, `json.loads` raises; Story 5.1 WSS consumer should catch and treat as invalid ticket (fail closed).

## Deferred from: code review of 5-1-realtime-sync-hocuspocus-yjs.md (2026-03-30)

- **Optional Hocuspocus/ticket automated tests not added**: Story 5.1 marks a Node integration test for ticket consume as optional; no new automated coverage was required for acceptance.

## Deferred from: code review of 5-4-automatic-snapshot-persistence.md (2026-03-30)

- **DLQ escalation vs explicit admin alert**: Explicit operator alert channel (pager/webhook/metrics) is deferred to a dedicated ops-observability story; current ERROR+DLQ visibility is sufficient for Story 5.4 scope.


## Deferred from: code review of story-13.1 (2026-04-13)
- Network I/O in `finally` block: performing multiple await calls inside `finally` is risky if broadcasts hang.
- Triple fallback in UI rendering: defensive coding taken to a paranoid, messy extreme.
- Z-index escalation strategy: hardcoding 10000 suggests a lack of a proper modal/portal strategy.

## Deferred from: code review of 14-1-restore-failure-signal-review-hardening.md (2026-04-13)
- [x] [Review][Defer] Unbounded S3 read in restore core [src/api/fastapi/main.py] — deferred, pre-existing. The snapshot retrieval logic performs an unbounded read from S3, which could lead to OOM with very large payloads.

## Deferred from: code review of 16-3-api-user-provisioning-and-rbac.md (2026-04-14)
- Keycloak/DB Transactionality Gap [src/api/fastapi/main.py:3766]: If Keycloak user creation succeeds but PostgreSQL ManagerMembership persistence fails, an orphaned user is created in Keycloak. Acceptable for v1 but needs future hardening.
- Missing Configuration Guard for Keycloak Issuer [src/api/fastapi/keycloak_admin.py:100]: KEYCLOAK_ISSUER environment variable might be missing or malformed, leading to KeyError or malformed URLs. Needs global config validation.

## Deferred from: code review of 16-5-ui-manager-invite-transcripteur-expert.md (2026-04-16)
- Hardcoded Localization: UI strings are hardcoded in French (consistent with project pattern but technically deferred technical debt).
- Extensive Inline Styles: Component relies heavily on style prop (consistent with Azure Flow pattern in project).

## Deferred from: code review of 17-1-demo-runbook-multi-role-e2e.md (2026-06-22)
- **asyncio.Lock() created at module level** [`src/api/fastapi/keycloak_admin.py:18`] — Safe on Python 3.10+ (current stack 3.11); would break on Python 3.9. Low risk unless the base image is downgraded.
- **Initial password plaintext in notification body** [`CreateManagerModal.tsx`, `InviteTeamMemberModal.tsx`] — Intentional design: no transactional email until Epic 18 (Notification Engine). Re-evaluate when Epic 18 is implemented.
- **`_safe_minio_read` stat→read TOCTOU** [`src/api/fastapi/main.py`] — Pre-existing; noted in deferred-work from review of 14-1. Object can be replaced between stat and get_object calls.
- **`_safe_minio_read` 413 size-guard path has no test coverage** [`src/api/fastapi/main.py`] — New safety feature added this story; the oversized-object rejection path is untested. Add a test that mocks stat_object returning a large size.
- **"Label Studio →" button silently absent when `label_studio_project_id` is null** [`src/frontend/src/features/dashboard/RoleDashboards.tsx`] — If a project was not provisioned to Label Studio, the button is hidden without diagnostic. This is a data integrity issue at provisioning; consider adding a tooltip or disabled state in a future UX story.

## Deferred from: code review of uncommitted 17.1 implementation patches (2026-06-22)

- **KA-5 — `list_keycloak_users` silent truncation** [`src/api/fastapi/keycloak_admin.py`] — Hard-coded `max=1000`; realms with >1000 users silently return incomplete data. Implement pagination (`first`/`max` loop) or raise when result set hits the cap.
- **MA-4 — `list_iam_users` full Keycloak attribute exposure** [`src/api/fastapi/main.py`] — Admin/Manager path returns raw Keycloak user objects (email, phone, custom attrs) with no field projection. Project only the fields the API contract needs before returning.
- **MA-8 — No Alembic migration for `assignments` schema change** — `Assignment` PK changed from auto-increment `id` to composite `(audio_id, transcripteur_id)`; `help_requested`/`help_message` columns added. No migration file exists. Write an Alembic migration before deploying against an existing DB.
- **MA-9 — `assigned_at` now means "latest assignment time"** [`src/api/fastapi/main.py:_audio_row_for_project_status`] — Breaking API contract change; existing clients expecting a single user ID for `assigned_to` will break. Consider returning `assigned_to` as a JSON array and adding `last_assigned_at` vs `first_assigned_at` fields, or version the endpoint.
- **MA-10 — Projects default to `ACTIVE` on creation** [`src/api/fastapi/main.py:create_project`] — Bypasses any draft→active promotion step; projects with zero valid audio files appear in task lists immediately. Revert to `DRAFT` default or add a readiness gate.
- **TF-6 — `onReconcile` callback ID not verified in test** [`src/frontend/src/features/dashboard/RoleDashboards.test.ts`] — Test only checks text presence via static markup; doesn't assert `onReconcile` is called with the correct `audio_id`. Add a jsdom-environment test that simulates the button click.

## Deferred from: code review of uncommitted 17.1 patches — round 3 (2026-06-22)

- **R3MA-5 — `claim_audio_task` no project-status guard** [`src/api/fastapi/main.py`] — A Transcripteur can claim audio from COMPLETED/ARCHIVED projects. Policy decision: DRAFT claiming is intentional (mirrors `list_available_tasks`), but COMPLETED project claiming is unclear. Add `Project.status == ProjectStatus.ACTIVE` guard once the project lifecycle is finalised.
- **R3TF-6 — Golden set webhook success-path test with `task.project` set** [`src/api/fastapi/test_api_sec_20_story_4_1_golden_set_label_studio_webhook_internal_ingest.py`] — No test covers the success path with a valid `task.project` that matches `af.project_id`. Add a positive test with `mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, proj_r, ctr_r])` where `proj.id == af.project_id == 1`.

## Deferred from: code review of uncommitted 17.1 patches — round 4 (2026-06-22)

- **R4MA-3 — `claim_audio_task` selectinload outside lock scope** [`src/api/fastapi/main.py`] — `selectinload(AudioFile.assignment)` fires a separate SELECT not covered by `with_for_update()`. Concurrent callers can insert between the locked AudioFile read and the unlocked Assignment read. The `IntegrityError` handler catches the resulting conflict; this is accepted as the primary race guard for now. Replace with an explicit locked existence query if the claim endpoint becomes high-concurrency.
