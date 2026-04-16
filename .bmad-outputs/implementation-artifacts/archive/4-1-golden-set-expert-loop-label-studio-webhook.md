# Story 4.1: Golden Set Capture — Expert Loop (Label Studio Webhook)

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created. -->

## Story

As the **System**,
I want to **receive a trusted webhook from Label Studio when expert work is submitted/validated** and **persist each validated segment as a Golden Set artifact** (database row + MinIO object with integrity metadata),
so that **high-weight expert annotations (`source: label_studio`, `weight: high`) feed the Flywheel** consistently with the Frontend loop (Story 4.2) and Camunda fine-tuning triggers (Stories 4.3–4.4).

---

## Traduction (FR)

**En tant que** système, **je veux** recevoir un webhook Label Studio lorsque l’expert valide/soumet une tâche et **archiver** chaque segment validé `{segment audio, texte corrigé, label, poids élevé}` dans le *Golden Set* (PostgreSQL + MinIO), **afin d’** alimenter le pipeline d’entraînement avec des annotations expertes fiables.

---

## Acceptance Criteria

1. **Callback HTTP (contract):** Implement `POST /v1/callback/expert-validation` as specified in [Source: `docs/api-mapping.md` §5 — `POST /v1/callback/expert-validation`]. Accept a body that is **either** the minimal contract `{task_id, annotation, audio_id}` **or** a normalized internal DTO after parsing a **Label Studio webhook envelope** (document the chosen LS event type(s), e.g. `TASKS_CREATED` / `ANNOTATION_CREATED` / `ANNOTATION_UPDATED` — pick the minimal set that means “expert validated for Golden Set”). Respond **2xx** only after **durable** persistence (DB + MinIO) succeeds; **4xx** for malformed or unauthenticated requests; **5xx** only on genuine server/IO failures (Label Studio will retry).

2. **Authn for webhooks:** Label Studio cannot send a user JWT. Protect the callback using a **shared secret** (e.g. `LABEL_STUDIO_WEBHOOK_SECRET` in header `X-ZachAI-Webhook-Secret` or `Authorization: Bearer <secret>`) validated in constant time. Reject missing/invalid secret with **401/403** without leaking details. Document the exact header name in `.env.example` and compose. *(If product later mandates mTLS, note as future hardening — not required for this story.)*

3. **Idempotency:** The same LS annotation / task completion may be delivered more than once. **De-duplicate** using a stable key (e.g. `(label_studio_annotation_id, task_id)` or hash of `(task_id, annotation_updated_at, result_json)` stored in DB). Second delivery must **not** double-increment counters or duplicate MinIO objects.

4. **Parsing — segments:** From Label Studio JSON, extract **one Golden Set entry per validated segment** with at minimum: `segment_start`, `segment_end`, `corrected_text`, `label` (string or null if schema has no label for that region), `audio_id` (ZachAI `audio_files.id`). Map `original_text` from Whisper pre-annotation when present in task data / `result` / `meta` (for audit and future training); if absent, store `null` and log once at `INFO`.

5. **`POST /v1/golden-set/entry` (internal service):** Implement the internal golden-set ingestion path per [Source: `docs/api-mapping.md` §4]. It must: **(a)** insert into PostgreSQL `golden_set_entries` (or equivalent table name matching existing naming in `main.py`), **(b)** write a JSON (or JSON Lines) artifact to MinIO under prefix **`golden-set/`** including checksum **SHA-256** of the canonical serialized payload in the object metadata or sidecar field, **(c)** increment **`golden_set_counter`** in **`golden_set_counters`** (or a single-row aggregate table — remain consistent with [Source: `docs/architecture.md` §3 — `GoldenSetEntry`, `GoldenSetCounter`]). **Do not** trigger Camunda LoRA from this story (Story 4.3).

6. **Weights and sources:** Force `source = "label_studio"` and `weight = "high"` for all entries ingested via this webhook path, matching [Source: `docs/architecture.md` §4 — two sources, two weights] and [Source: `docs/prd.md` §4.4 expert loop].

7. **Referential integrity:** Reject with **404** if `audio_id` does not exist. Optionally verify `audio_files.project_id` matches the Label Studio project mapped via `projects.label_studio_project_id` when `task` carries `project` id — prevents cross-project contamination.

8. **MinIO layout:** Use object keys under `golden-set/` that are **unique** and sortable, e.g. `golden-set/{audio_id}/{entry_uuid}.json` (or include date partition `golden-set/yyyy/mm/{audio_id}/...`). Must comply with existing presigned GET allowlist pattern `golden-set/` [Source: `src/api/fastapi/main.py` — `ALLOWED_GET_PREFIXES`].

9. **Observability:** Structured logs: `audio_id`, `task_id`, `entries_written`, `idempotency_hit`, `minio_key`, `duration_ms`. Never log raw secrets or full JWTs.

10. **Tests:** Add unit/integration tests in `test_main.py` (or split only if `main.py` is already unmaintainable — prefer small helpers in the same package first): **valid** webhook → DB row + MinIO put mocked; **wrong secret** → 401/403; **duplicate** webhook → single counter increment; **missing audio** → 404. Use existing httpx client / DB test patterns from prior stories.

---

## Tasks / Subtasks

- [x] **Task 1 (Schema)** — Add SQLAlchemy models + migrations/init path for `GoldenSetEntry` and `GoldenSetCounter` aligned with [Source: `docs/architecture.md` §3]. Include unique constraint or partial index supporting idempotency key.
- [x] **Task 2 (Internal API)** — Implement `POST /v1/golden-set/entry` protected by **internal** auth (service API key env `GOLDEN_SET_INTERNAL_SECRET` or reuse a single `INTERNAL_CALLBACK_SECRET` — document one approach; must differ from public user JWT validation path).
- [x] **Task 3 (MinIO writer)** — Reuse existing MinIO client helpers in `main.py`; write canonical JSON bytes; compute SHA-256; set metadata or embed `sha256` field per [Source: `docs/prd.md` §6.2 integrity].
- [x] **Task 4 (LS webhook)** — Implement `POST /v1/callback/expert-validation`: verify secret → parse LS payload → resolve `audio_id` (from LS task `data` / `meta` / naming convention agreed in Story 2.2/2.x task import — **document the binding**: e.g. task field `audio_id` set when tasks are synced) → map annotations → call internal golden-set ingestion.
- [x] **Task 5 (Label Studio config note)** — Document in Dev Notes how ops register the webhook URL in Label Studio UI (Project Settings → Webhooks) pointing at FastAPI via internal Docker URL or edge URL.
- [x] **Task 6 (Compose / env)** — Add env vars to `src/.env.example` and `compose.yml` for FastAPI: webhook secret, internal golden-set secret, optional `GOLDEN_SET_BUCKET` default `golden-set`.

### Review Findings (AI — 2026-03-29)

**Decision-needed (resolved):**

- [x] [Review][Decision] **Multi-segment atomicity** — Resolved: **Option B** — accept partial success, rely on idempotent LS retry. MinIO has no transactional semantics; idempotency keys guarantee correct final state. Added comment documenting retry contract.
- [x] [Review][Decision] **Webhook action type is ignored** — Resolved: **Option A** — added allowlist (`ANNOTATION_CREATED`, `ANNOTATION_UPDATED`, `ANNOTATION_SUBMITTED`); other actions return 200 no-op.
- [x] [Review][Decision] **Secrets not in REQUIRED_ENV_VARS** — Resolved: **Option B** — keep 503 graceful degradation. Matches tolerant startup pattern for Camunda/FFmpeg.

**Patch (all applied):**

- [x] [Review][Patch] **MinIO object orphaned on DB commit failure** — Added compensating `remove_object` in `except Exception` block after rollback.
- [x] [Review][Patch] **`label_studio_project_id_from_task` ignores integer `task.project`** — Added `isinstance(p, int)` branch.
- [x] [Review][Patch] **`segment_start`/`segment_end` accepts NaN, Inf, negative, inverted** — Added `ge=0`, `isfinite` validator, `model_validator` for `start <= end`; `_coerce_float` now rejects non-finite.
- [x] [Review][Patch] **`GOLDEN_SET_THRESHOLD` crashes on non-numeric env var** — Wrapped in try/except with fallback to 1000.
- [x] [Review][Patch] **Auth verification duplicated** — Extracted `_verify_shared_secret()` parameterized helper.
- [x] [Review][Patch] **MinIO object keys not sortable (AC8)** — Keys now use `{audio_id}/{yyyymmddTHHMMSSZ}_{hex12}.json`.
- [x] [Review][Patch] **Fallback 0.0–0.0 synthetic segment** — Removed; textarea-only annotations return empty list with DEBUG log.
- [x] [Review][Patch] **Internal endpoint missing no-auth 401 test** — Added `test_golden_set_internal_entry_no_auth_header`.
- [x] [Review][Patch] **INFO log for missing `original_text` is noisy** — Downgraded to DEBUG.
- [x] [Review][Patch] **`GOLDEN_SET_THRESHOLD` missing from compose.yml** — Added `GOLDEN_SET_THRESHOLD: ${GOLDEN_SET_THRESHOLD:-1000}`.
- [x] [Review][Patch] **`audio_id ≤ 0` from LS causes unhandled 500** — Added explicit `audio_id <= 0` guard returning 400 before constructing Pydantic model.
- [x] [Review][Patch] **Counter row insert race** — Counter insert wrapped in try/except IntegrityError with re-select fallback.

**Deferred:**

- [x] [Review][Defer] Auth verification as imperative calls, not FastAPI `Depends()` — pre-existing pattern
- [x] [Review][Defer] No request body size limit on webhook endpoint — operational concern, default limits exist
- [x] [Review][Defer] Test env vars set globally via `os.environ.setdefault` — pre-existing test pattern
- [x] [Review][Defer] `source`/`weight` not validated at DB level — pre-existing design pattern, Pydantic is only gate

---

## Dev Notes

### Scope boundaries

- **In scope:** Expert Loop ingestion only (Label Studio → FastAPI → PostgreSQL + MinIO + counter).
- **Out of scope:** LoRA trigger (4.3), full training pipeline (4.4), Frontend correction loop (4.2), Manager validation chain (Epic 6), Camunda changes beyond env readiness.

### Cross-story dependencies

- **Depends on:** Story **2.2** (Label Studio project id on `projects.label_studio_project_id`), Story **1.3** (presigned patterns), Story **3.2/3.3** (Whisper pre-annotation exists in task payloads if LS tasks are created with prediction data).
- **Unlocks:** Story **4.3** (counter threshold → Camunda) once counter semantics are stable.

### Label Studio payload reality check

Label Studio webhook JSON typically wraps `event`, `task`, `annotation`, `project`. The dev agent **must** inspect the **actual** payload from LS version used in `compose.yml` (pin doc note) and add a small **adapter function** (`normalize_ls_webhook(body: dict) -> list[GoldenSegment]`) rather than assuming flat fields. If `audio_id` is not yet present on imported tasks, follow up with a thin **task import** amendment in sync code **or** encode `audio_id` in `task.data` during audio → LS export (cite the code path once identified).

### Label Studio webhook registration (ops) — Story 4.1 Task 5

1. In **Label Studio** open the target project → **Settings** → **Webhooks**.
2. **Payload URL:** `http://fastapi:8000/v1/callback/expert-validation` on the Docker network (service name from `compose.yml` is `fastapi`; use your public edge URL if LS runs outside Compose).
3. Enable events such as **ANNOTATION_UPDATED** / **ANNOTATION_CREATED** (exact list varies slightly by Label Studio major version; choose events fired when an expert saves or submits annotations).
4. Add HTTP header **`X-ZachAI-Webhook-Secret`** with the same value as environment variable `LABEL_STUDIO_WEBHOOK_SECRET` on FastAPI. Alternatively send **`Authorization: Bearer <same secret>`**.
5. **audio_id binding:** Each task must include ZachAI’s integer `audio_id` in **`task.data.audio_id`** when tasks are created, **or** callers may use the minimal JSON contract with top-level **`audio_id`**. Until import/sync writes `task.data.audio_id`, this webhook cannot resolve storage (`400` with a clear error). *No LS→task sync path existed in-repo at 4.1 implementation time; this field must be set by a future import worker or manual API sync.*

### Project Structure Notes

- Primary touchpoint: `src/api/fastapi/main.py` (models, deps, routes).
- PostgreSQL schema: align with existing `Base.metadata.create_all` / startup migration pattern used for `Nature`, `Project`, `AudioFile`, `Assignment` — **do not** introduce a second DB framework without cause.
- MinIO bucket `golden-set` already expected in bootstrap [Source: `src/compose.yml` mc init].

### References

- [Source: `docs/epics-and-stories.md` — Epic 4, Story 4.1]
- [Source: `docs/prd.md` §4.4, §4.6, §6.2, §6.4]
- [Source: `docs/architecture.md` §1–§4, diagram Golden Set path `LS -->|Validation webhook| API`]
- [Source: `docs/api-mapping.md` §4–§5]
- [Source: `docs/ux-design.md` §5.C — expert corrections feed Flywheel (product context only; no UI in this story)]

---

## Technical Requirements

| Area | Requirement |
|------|-------------|
| API style | Match existing FastAPI patterns: Pydantic models, `HTTPException`, role checks where applicable |
| DB | Async SQLAlchemy session pattern already in `main.py` — extend consistently |
| Security | Webhook secret + internal-only golden-set entry endpoint; never expose internal secret to browser |
| Integrity | SHA-256 over canonical JSON bytes before MinIO PUT [Source: `docs/prd.md` §6.2] |
| Performance | Batch MinIO writes if one webhook carries many segments; single DB transaction per webhook when practical |

---

## Architecture Compliance

| Source | Compliance |
|--------|------------|
| `docs/architecture.md` §4 | `source: label_studio`, `weight: high` |
| `docs/architecture.md` diagram | `LS \| Validation webhook \| API` |
| `docs/prd.md` §4.6 | Counter increments per validated pair; **no** Camunda start in 4.1 |
| Internal Shield | Callback route is server-to-server; still validate secret |

---

## Library / Framework Requirements

- Reuse stack already in FastAPI service: **SQLAlchemy 2**, **Pydantic**, **httpx** (if fetching supplementary task from LS API — optional; prefer stateless webhook if payload sufficient), **MinIO** Python SDK as in `main.py`.
- Do **not** add heavy new dependencies unless required for SHA-256 (use `hashlib` stdlib).

---

## File Structure Requirements

```
src/
├── api/fastapi/
│   ├── main.py                    ← MODIFY (models, routes, helpers)
│   └── test_main.py              ← MODIFY (new tests)
├── compose.yml                   ← MODIFY (FastAPI env)
└── .env.example                  ← MODIFY (webhook + internal secrets)
```

Optional (only if `main.py` becomes unwieldy): `src/api/fastapi/golden_set.py` for parsing — keep imports cycle-free.

---

## Testing Requirements

- Mock MinIO (`unittest.mock` or pytest fixtures) consistent with prior stories.
- Test idempotency: two identical webhook posts → one DB row count delta / one counter increment.
- Test **audio_id** FK rejection.

---

## Previous Story Intelligence

- **No prior story in Epic 4.** Nearest codebase patterns: Story **2.2** Label Studio API + project linkage; Story **3.3** MinIO pointer patterns (Golden Set writes are **new** but bucket conventions align with Story **1.1**).

---

## Git Intelligence Summary

Recent commits emphasize **OpenVINO worker**, **model registry**, **assignment dashboard** — **no** golden-set code yet. This story is greenfield inside FastAPI + DB schema.

---

## Latest Technical Information

- **Label Studio Webhooks:** Configure in project settings; payload includes annotation JSON. Validate against the image version in compose (document version in story implementation notes when pinned).
- **Webhook security:** Use shared secret header; rotate via env in deployments.

---

## Project Context Reference

- No `project-context.md` found in repo root search — rely on `docs/*.md` + `.bmad-outputs/implementation-artifacts/*` for patterns.

---

## Dev Agent Record

### Agent Model Used

Cursor agent (Auto) — implementation per `bmad-dev-story` workflow.

### Debug Log References

- Initial pytest failures: `uuid` import accidentally dropped when adding golden-set imports; restored `import uuid`.

### Completion Notes List

- Added `GoldenSetEntry` / `GoldenSetCounter` ORMs, unique `idempotency_key`, startup seed for counter row `id=1`.
- Implemented `persist_golden_set_entry`: idempotency pre-check + optional Label Studio project cross-check, MinIO `put_object` to `GOLDEN_SET_BUCKET` under `{audio_id}/{uuid}.json`, SHA-256 of core payload (embedded `sha256` + `x-amz-meta-sha256`), counter increment only on new rows; no Camunda.
- `POST /v1/golden-set/entry` uses `GOLDEN_SET_INTERNAL_SECRET` via `X-ZachAI-Golden-Set-Internal-Secret` or `Authorization: Bearer`.
- `POST /v1/callback/expert-validation` uses `normalize_expert_validation_payload` in `golden_set.py` (LS envelope + minimal `{task_id, annotation, audio_id}`); forces `source=label_studio` / `weight=high`.
- Dockerfile copies `golden_set.py`; compose + `.env.example` document secrets and bucket.
- Tests in `test_main.py`: 401/403 webhook auth, 404 missing audio, happy path + idempotent hit, internal endpoint auth.

### File List

- `src/api/fastapi/main.py`
- `src/api/fastapi/golden_set.py`
- `src/api/fastapi/test_main.py`
- `src/api/fastapi/Dockerfile`
- `src/compose.yml`
- `src/.env.example`

### Change Log

- **2026-03-29:** Story 4.1 — Golden Set expert loop (DB + MinIO + webhook + internal ingest + tests).

---

## Story Completion Status

**done** — Implementation complete + code review patches applied; full `test_main.py` suite passing (89 tests).
