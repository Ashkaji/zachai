# Story 4.2: Golden Set Capture — User Loop (Frontend Corrections)

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created. -->

## Story

As the **System**,
I want to **capture text corrections made in the Tiptap editor** (using **inline ProseMirror marks** that carry audio segment time bounds) and **persist** each correction as `{segment_start, segment_end, original_whisper, corrected_text, source: frontend_correction, weight: standard}` in the Golden Set **(PostgreSQL + MinIO + counter)** via an authenticated browser API,
so that **transcripteur edits contribute to the Flywheel** alongside the Expert Loop (Story 4.1) and future LoRA triggers (Stories 4.3–4.4).

---

## Traduction (FR)

**En tant que** système, **je veux** capturer les corrections de texte effectuées dans l’éditeur Tiptap (marks ProseMirror inline portant les bornes temporelles) et **enregistrer** chaque correction `{segment_start, segment_end, texte Whisper d’origine, texte corrigé, source: frontend_correction, poids: standard}` dans le *Golden Set* via une API navigateur authentifiée, **afin que** les corrections des transcripteurs alimentent le *Flywheel* comme la boucle experte (4.1) et les prochains déclenchements LoRA (4.3–4.4).

---

## Acceptance Criteria

1. **Transcripteur-only API (JWT):** Expose `POST /v1/golden-set/frontend-correction` (name may be merged into a single `/v1/golden-set/entry` with dual auth **only if** OpenAPI and code comments clearly separate “internal webhook secret” vs “user JWT” — prefer a **dedicated path** for browser calls). **Auth:** valid Keycloak JWT; caller must have role **Transcripteur** (or **Admin** for support). **Body** (minimum): `audio_id` (int), `segment_start`, `segment_end` (float, seconds), `original_text` (string; Whisper baseline), `corrected_text` (string), optional `label` (string | null). **Forbidden:** clients must **not** send `source` / `weight`; server **forces** `source = "frontend_correction"` and `weight = "standard"` per [Source: `docs/architecture.md` §4].

2. **Assignment gate:** Reject **403** if the JWT `sub` is not the `Assignment.transcripteur_id` for the given `audio_id`, unless role is **Admin**. Reject **404** if `audio_id` does not exist. Optionally reject **409** if `AudioFile.status` is not in `{assigned, in_progress}` (product policy: no Golden Set churn after submit — align with [Source: `docs/prd.md` §4.5] and existing assign rules in `main.py`).

3. **Reuse Golden Set persistence:** Call the **same** ingestion routine implemented for Story **4.1** (DB insert `GoldenSetEntry`, MinIO object under `golden-set/`, SHA-256 on canonical bytes, `GoldenSetCounter` increment). **Do not** duplicate MinIO/DB logic in a second code path. If Story 4.1 is not merged yet, implement **one** internal function (e.g. `persist_golden_set_entry(...)`) and use it from both the Label Studio callback and this route.

4. **No Camunda in this story:** Do not start LoRA / threshold Camunda flows here (Story 4.3). Counter increment only.

5. **Idempotency (recommended):** Accept optional `client_mutation_id` (UUID string). If the same `(audio_id, client_mutation_id)` is submitted twice, second request must be a **no-op** for counter + no duplicate MinIO object (same pattern as Story 4.1 idempotency key).

6. **Frontend — minimal Tiptap slice:** There is **no** `package.json` in the repo today; add **`src/frontend/`** (Vite + React + TypeScript + Tiptap v2). Custom **Mark** extension (e.g. `WhisperSegment`) with attrs at minimum: `audioStart`, `audioEnd` (float), `sourceText` (string — initial Whisper text for the span). **Seeding:** Build initial editor JSON from Whisper segments (see AC7). **Capture:** On text change inside a marked range, debounce (e.g. 500–1000 ms) and `POST` the diff with `original_text` from the mark’s `sourceText` (or from last acknowledged server state) and `corrected_text` from current slice text. Document how paste/split marks behave (see Dev Notes).

7. **Transcription data for editor bootstrap:** If `GET` (or equivalent) for **stored segments** for an `audio_id` does not exist on FastAPI yet, add **`GET /v1/audio-files/{audio_file_id}/transcription`** (or under `/v1/me/...`) returning `{ "segments": [ { "start", "end", "text", "confidence?"] } ]` from the same persistence the OpenVINO worker will populate via `POST /v1/callback/transcription` [Source: `docs/api-mapping.md` §5]. **Until** the callback persists rows, the endpoint may return **`{ "segments": [] }`** with **200**; the frontend must still run for manual E2E using a **dev fixture** documented in Dev Notes. **Auth:** Transcripteur assigned to that audio (same rule as AC2).

8. **Observability:** Structured logs: `audio_id`, `user_sub`, `segment_start`, `segment_end`, `entries_written`, `idempotency_hit`, `minio_key`, `duration_ms`. Never log full JWTs.

9. **Tests (FastAPI):** Extend `test_main.py`: **happy path** Transcripteur → 2xx + counter/DB (MinIO mock); **wrong user** → 403; **wrong role** (e.g. Manager only) → 403; **missing audio** → 404; optional idempotency duplicate.

10. **Docs / contract:** Update [Source: `docs/api-mapping.md` §4] with the new route and auth model. Add `src/frontend/README.md` (short: env `VITE_API_BASE`, OIDC PKCE pointer to existing Keycloak client from [Source: `src/config/realms/zachai-realm.json`]).

---

## Tasks / Subtasks

- [x] **Task 1 (Backend route)** — Implement `POST /v1/golden-set/frontend-correction` with JWT + assignment checks; delegate to shared `persist_golden_set_entry` from Story 4.1 pattern.
- [x] **Task 2 (Transcription read)** — Implement `GET .../transcription` for an audio file with Transcripteur scoping; align JSON with PRD §6.4 segment shape [Source: `docs/prd.md` §6.4].
- [x] **Task 3 (Frontend scaffold)** — `src/frontend/` Vite/React/TS; Tiptap + custom mark; OIDC token attached to `fetch` (PKCE); debounced submission.
- [x] **Task 4 (Compose / env)** — Optional `frontend` service in `compose.yml` (dev profile) or document `npm run dev` against `VITE_API_BASE=http://localhost:8000`; add any new FastAPI env vars only if needed (none expected beyond existing JWT validation).

### Review Findings

- [x] [Review][Decision] **D1 — CASCADE DELETE on GoldenSetEntry FK** — dismissed: keep CASCADE per user decision (training data disposable with audio)
- [x] [Review][Decision] **D2 — Extra `source`/`weight` in request body silently ignored** — dismissed: keep permissive ignore; server forces correct values
- [x] [Review][Patch] **P1 — OIDC callback strips `audio_id` query param** — fixed: preserve query params, strip only OIDC params
- [x] [Review][Patch] **P2 — No `max_length` on `original_text`/`corrected_text`** — fixed: added max_length=50000 on both schemas
- [x] [Review][Patch] **P3 — Frontend never sends `client_mutation_id`** — fixed: generates crypto.randomUUID() per correction
- [x] [Review][Patch] **P4 — IntegrityError idempotency race doesn't clean up MinIO blob** — fixed: added remove_object in IntegrityError handler
- [x] [Review][Patch] **P5 — Counter increment uses Python read-modify-write, not SQL expression** — fixed: uses GoldenSetCounter.count + 1
- [x] [Review][Patch] **P6 — `corrected_text` defaults to empty string on internal schema** — fixed: added max_length cap; FrontendCorrectionRequest enforces min_length=1
- [x] [Review][Patch] **P7 — `audio_id` NaN when query param is non-numeric** — fixed: validates parseInt result with Number.isNaN
- [x] [Review][Patch] **P8 — Debounce timeout not cleared on component unmount** — fixed: cleanup in useEffect return
- [x] [Review][Patch] **P9 — `lastSentRef` key collision for segments with same time bounds** — fixed: includes sourceText in key
- [x] [Review][Patch] **P10 — `_verify_shared_secret` reads env var on every request** — fixed: cached at module level
- [x] [Review][Patch] **P11 — `changeme-*` default secrets with no startup validation** — fixed: logs warning at startup for default values
- [x] [Review][Patch] **P12 — `_GOLDEN_SET_ACTIONS` set defined inside handler body** — fixed: moved to module-level frozenset
- [x] [Review][Patch] **P13 — `GOLDEN_SET_THRESHOLD` silent fallback on invalid value** — fixed: logs warning on parse error
- [x] [Review][Patch] **P14 — Empty Bearer token candidate → 403 instead of 401** — fixed: filters empty candidates via list comprehension
- [x] [Review][Patch] **P15 — `CORS_ALLOWED_ORIGINS` not in `.env.example` or `compose.yml`** — fixed: added to both
- [x] [Review][Patch] **P16 — MinIO `put_object` non-S3Error unhandled** — fixed: catches Exception instead of S3Error
- [x] [Review][Defer] **W1 — Expert webhook serializes N DB/MinIO round-trips** — deferred, Story 4.1 design
- [x] [Review][Defer] **W2 — No Alembic/migration tool** — deferred, pre-existing architectural choice
- [x] [Review][Defer] **W3 — No rate limiting on correction endpoint** — deferred, infrastructure concern
- [x] [Review][Defer] **W4 — Redundant guard in `normalize_expert_validation_payload`** — deferred, Story 4.1 helper
- [x] [Review][Defer] **W5 — LS project verification silently passes for unknown project** — deferred, Story 4.1 code path
- [x] [Review][Defer] **W6 — Frontend sequential correction submission** — deferred, performance optimization for future story
- [x] [Review][Patch] **P17 — Webhook segment `start > end` causes uncaught ValidationError** — fixed: try/except around GoldenSetEntryRequest construction, skips invalid segments
- [x] [Review][Patch] **P18 — `client_mutation_id` was fresh UUID per call, not stable per retry** — fixed: deterministic ID from segment identity + text
- [x] [Review][Patch] **P19 — `parseInt("12abc")` returns 12, partial numeric accepted** — fixed: strict `/^\d+$/` regex test
- [x] [Review][Defer] **W7 — `GOLDEN_SET_THRESHOLD` accepts 0 or negative** — deferred, threshold not consumed until Story 4.3
- [x] [Review][Defer] **W8 — `api-mapping.md` describes Camunda trigger but code doesn't fire it** — deferred, pre-existing docs text

---

## Dev Notes

### Scope boundaries

- **In scope:** User-loop Golden Set capture from Tiptap corrections + FastAPI persistence + minimal editor shell.
- **Out of scope:** Hocuspocus/Yjs (Epic 5), karaoke audio player polish (Epic 5), LanguageTool (5.5), LoRA / Camunda threshold (4.3–4.4), Manager validation chain (Epic 6).

### Cross-story dependencies

- **Depends on:** Story **4.1** (schema + MinIO layout + counter + internal ingestion). Implement **after** 4.1 or in the same branch with shared helper.
- **Coordinates with:** Story **3.2** worker → **`/v1/callback/transcription`** persistence (may still be open; transcription GET then returns data once wired).
- **Unlocks:** Story **4.3** (threshold) consuming the same counter.

### ProseMirror / Tiptap reality check

- Marks must remain **atomic** where possible so segment bounds stay tied to text [Source: `docs/architecture.md` §4 — resilient timestamps].
- On **paste** or **mark split**, either re-merge spans in a `appendTransaction` plugin or submit **smaller** adjacent corrections; document chosen behavior to avoid orphan timestamps.

### Project Structure Notes

- Backend: `src/api/fastapi/main.py` (routes, deps); tests `src/api/fastapi/test_main.py`.
- Frontend: new tree under `src/frontend/` (do not scatter ad-hoc scripts at repo root).

### References

- [Source: `docs/epics-and-stories.md` — Epic 4, Story 4.2]
- [Source: `docs/prd.md` §4.3, §4.6, §6.2, §6.4]
- [Source: `docs/architecture.md` §2 diagram `Prod -->|Correction diff| API`, §3–§4]
- [Source: `docs/api-mapping.md` §4–§5]
- [Source: `docs/ux-design.md` §5 — feedback loop / correction journey]

---

## Technical Requirements

| Area | Requirement |
|------|-------------|
| Auth | Keycloak JWT validation consistent with existing `get_current_user` / `get_roles` in `main.py` |
| Authorization | Transcripteur may only POST for assigned `audio_id`; Admin override documented |
| Golden Set | Same SHA-256 + `golden-set/` prefix + counter semantics as Story 4.1 |
| Frontend | TypeScript strict; Tiptap extensions documented; no secret keys in browser |

---

## Architecture Compliance

| Source | Compliance |
|--------|------------|
| `docs/architecture.md` §4 | `source: "frontend_correction"`, `weight: "standard"` |
| Diagram | `Prod -->|Correction diff| API` |
| `docs/prd.md` §4.3 | Corrections → Golden Set pairs with inline timestamps |

---

## Library / Framework Requirements

- **Backend:** Existing stack only (FastAPI, SQLAlchemy, Pydantic, MinIO, `python-jose`, `httpx` as already in service).
- **Frontend:** Vite 5+, React 18+, TypeScript, **Tiptap v2** (`@tiptap/react`, `@tiptap/starter-kit` + custom Mark). Use **openid-client** or **react-oidc-context** for PKCE — align with Keycloak public client `"zachai-frontend"` in realm JSON if present.

---

## File Structure Requirements

```
src/
├── api/fastapi/
│   ├── main.py              ← MODIFY (routes, ingestion helper if shared)
│   └── test_main.py       ← MODIFY
├── frontend/                ← NEW (Vite app)
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── editor/        ← Tiptap + WhisperSegment mark + debounced POST
│   │   └── auth/          ← OIDC token for API calls
│   └── README.md
├── compose.yml              ← OPTIONAL: frontend service
└── docs/api-mapping.md     ← MODIFY (new route)
```

---

## Testing Requirements

- Backend: pytest + httpx test client patterns already in `test_main.py`; mock MinIO where 4.1 tests do.
- Frontend: at minimum `npm run build` CI gate; optional Vitest for mark parsing utility if extracted.

---

## Previous Story Intelligence

- **Story 4.1** defines Label Studio webhook path, **internal** golden-set secret, idempotency, MinIO key layout, and `GoldenSetEntry` / `GoldenSetCounter` — **reuse** that design for user-loop rows differing only by `source` / `weight` and auth path [Source: `.bmad-outputs/implementation-artifacts/4-1-golden-set-expert-loop-label-studio-webhook.md`].
- **Story 2.4** established `Assignment`, `/v1/me/audio-tasks`, and transcripteur **sub** scoping — mirror those patterns for AC2.

---

## Git Intelligence Summary

- Recent work: OpenVINO worker (3.2), model registry (3.3), assignment dashboard (2.4). **No** Golden Set or React app in tree yet — this story introduces **both** the browser capture path and the first frontend package.

---

## Latest Technical Information

- **Tiptap v2:** Use documented Mark + `mergeAttributes` for `audioStart` / `audioEnd`; verify compatibility with React 18 strict mode (double mount) — prefer idempotent editor init.
- **Keycloak JS:** Prefer short-lived access token refresh before `fetch` to FastAPI.

---

## Project Context Reference

- No `project-context.md` found — rely on `docs/*.md` and implementation artifacts under `.bmad-outputs/implementation-artifacts/`.

---

## Dev Agent Record

### Agent Model Used

Claude claude-4.6-opus-high-thinking (Cursor Agent mode)

### Debug Log References

No blockers encountered during implementation.

### Completion Notes List

- **Task 1:** Added `FrontendCorrectionRequest` Pydantic schema (clients cannot set `source`/`weight`; server forces `frontend_correction` / `standard`). Implemented `POST /v1/golden-set/frontend-correction` with JWT auth (Transcripteur or Admin), assignment gate (403 if not assigned), 404 if audio missing, 409 if status not in `{assigned, in_progress}`, optional `client_mutation_id` idempotency. Delegates to shared `persist_golden_set_entry`. Structured logging with `audio_id`, `user_sub`, segment bounds, `entries_written`, `idempotency_hit`, `minio_key`, `duration_ms`.
- **Task 2:** Added `GET /v1/audio-files/{audio_file_id}/transcription` with same Transcripteur-scoping as AC2. Returns `{"segments": []}` (200) until the OpenVINO callback persists transcription rows. Frontend uses a dev fixture when server returns empty.
- **Task 3:** Created `src/frontend/` scaffold: Vite 6 + React 18 + TypeScript 5 strict + Tiptap v2. Custom `WhisperSegment` Mark extension with `audioStart`, `audioEnd`, `sourceText` attributes. Editor loads segments from the transcription GET endpoint (dev fixture fallback). On text change inside a marked range, debounces 800ms and POSTs diff to `POST /v1/golden-set/frontend-correction`. OIDC PKCE via `react-oidc-context` / `oidc-client-ts`, pointing at Keycloak `zachai-frontend` public client. Mark splitting documented: contiguous spans with same time attributes are merged before diff comparison.
- **Task 4:** Added CORS middleware to FastAPI (`CORS_ALLOWED_ORIGINS` env var, defaults to `localhost:5173,localhost:3000`). Updated `docs/api-mapping.md` §4 with new routes and auth model. Added `src/frontend/README.md` with env vars, OIDC PKCE pointer, dev instructions. Documented optional `frontend` service in `compose.yml` (commented out, dev mode preferred). Added `.gitignore` for `node_modules/` and `dist/`.
- **Tests:** 12 new tests added to `test_main.py` — 7 for frontend correction route (happy path, wrong user 403, wrong role 403, missing audio 404, idempotent duplicate, admin bypass, status 409) + 5 for transcription GET (happy path, wrong user 403, missing audio 404, manager forbidden 403, admin can view). All 101 tests pass with zero regressions. `tsc --noEmit` and `vite build` both succeed.

### File List

- `src/api/fastapi/main.py` — MODIFIED (new routes, CORS, `FrontendCorrectionRequest` schema, version bump to 2.6.0)
- `src/api/fastapi/test_main.py` — MODIFIED (12 new tests for Story 4.2)
- `src/frontend/package.json` — NEW
- `src/frontend/tsconfig.json` — NEW
- `src/frontend/vite.config.ts` — NEW
- `src/frontend/index.html` — NEW
- `src/frontend/.gitignore` — NEW
- `src/frontend/README.md` — NEW
- `src/frontend/src/main.tsx` — NEW
- `src/frontend/src/App.tsx` — NEW
- `src/frontend/src/vite-env.d.ts` — NEW
- `src/frontend/src/auth/oidc-config.ts` — NEW
- `src/frontend/src/auth/api-client.ts` — NEW
- `src/frontend/src/editor/WhisperSegmentMark.ts` — NEW
- `src/frontend/src/editor/TranscriptionEditor.tsx` — NEW
- `src/compose.yml` — MODIFIED (frontend service documentation)
- `docs/api-mapping.md` — MODIFIED (new routes §4)

### Change Log

- 2026-03-29: Story 4.2 implementation complete — backend routes, frontend scaffold, tests, docs.

---

## Story Completion Status

**done** — All tasks complete, code review patches applied, all findings resolved.
