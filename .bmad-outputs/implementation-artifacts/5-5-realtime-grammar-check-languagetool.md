# Story 5.5: realtime-grammar-check-languagetool

Status: done

<!-- Best-effort context synthesis from existing implementation artifacts because dedicated planning artifacts were unavailable at creation time. -->

## Story
**As a** Transcripteur,  
**I want** spelling and grammar issues highlighted in real time while editing, with contextual suggestions I can apply quickly,  
**so that** I improve linguistic quality without breaking collaborative flow.

## Acceptance Criteria
1. **Debounced grammar checks from editor**
   1. Given a user is editing a document in the collaborative editor,
   2. When text changes and user pauses typing for the configured debounce window (target 500ms),
   3. Then the frontend sends a grammar check request to FastAPI `POST /v1/proxy/grammar` with `{text, language}` for the active document context,
   4. And repeated rapid edits do not trigger request storms.

2. **FastAPI proxy contract + authorization**
   1. Given `POST /v1/proxy/grammar` is called,
   2. Then FastAPI enforces JWT auth and role checks aligned with editor usage (`Transcripteur`, `Expert`, `Admin` support),
   3. And validates payload shape (non-empty `text`, bounded length, supported `language` format),
   4. And forwards the request to LanguageTool over internal network only.

3. **Result mapping and UX highlighting**
   1. Given LanguageTool returns matches,
   2. Then the frontend renders spelling issues with red wavy underline and grammar/style issues with orange/yellow wavy underline,
   3. And each issue exposes a contextual suggestion action (floating menu / bubble action) to apply one suggestion,
   4. And applying a suggestion updates only intended text range.

4. **Failure path and graceful degradation**
   1. Given LanguageTool is unavailable, rate-limited, or timing out,
   2. Then FastAPI returns a controlled error (`429` fallback path or explicit 5xx proxy failure semantics),
   3. And frontend remains editable, surfaces a non-blocking status, and does not crash collaboration.

5. **Caching and performance guardrail**
   1. Given frequent repeated checks on same `(text, language)`,
   2. Then FastAPI uses Redis-backed cache (TTL 5 min target) to reduce LanguageTool load,
   3. And end-to-end check latency remains suitable for real-time guidance (no observable editor freeze).

6. **No CRDT regressions**
   1. Grammar highlights and suggestion UI must be presentation-only state (decorations/client state),
   2. And must not introduce unintended Yjs document churn, callback storms, or Golden Set correction spam,
   3. Reusing anti-regression principles from Story 5.3 and 5.4.

7. **Out of scope (explicit)**
   1. Advanced style rewriting/paraphrasing beyond LanguageTool suggestions.
   2. Non-editor channels (Label Studio grammar assistance).

## Tasks / Subtasks
- [x] **Backend: implement grammar proxy endpoint** (AC: 2, 4, 5)
  - [x] Add/complete `POST /v1/proxy/grammar` in `src/api/fastapi/main.py` with strict request model validation.
  - [x] Enforce role gates consistent with editor flows (`Transcripteur`, `Expert`, `Admin`).
  - [x] Forward to LanguageTool service URL from env (`LANGUAGETOOL_URL` or equivalent), bounded timeout, and structured error mapping.
  - [x] Add Redis cache key strategy (text hash + language) with TTL 300s.
  - [x] Add logs/metrics fields: request duration, cache hit/miss, upstream status.

- [x] **Backend: compose/env wiring for LanguageTool** (AC: 2, 4, 5)
  - [x] Activate `languagetool` service in `src/compose.yml` with healthcheck and resource limits.
  - [x] Ensure FastAPI env wiring includes grammar proxy URL and cache settings.
  - [x] Update `src/.env.example` and `README.md` for required variables and operational guidance.

- [x] **Frontend: debounced check and overlay rendering** (AC: 1, 3, 6)
  - [x] Add debounced grammar check trigger in `src/frontend/src/editor/TranscriptionEditor.tsx` (or adjacent editor module).
  - [x] Render non-mutating grammar decorations/marking strategy in editor (no persisted content mutation for visual-only state).
  - [x] Distinguish issue classes (spelling vs grammar/style) by UX color rules from `docs/ux-design.md`.
  - [x] Ensure stale responses are ignored when newer text revision exists (request versioning/abort controller).

- [x] **Frontend: suggestion action UX** (AC: 3, 6)
  - [x] Add contextual suggestion menu action for highlighted issue.
  - [x] Apply selected suggestion deterministically to exact text span; preserve cursor/selection behavior as much as possible.
  - [x] Keep collaboration stable under concurrent edits and remote updates.

- [x] **Automated tests** (AC: 1-6)
  - [x] Backend tests in `src/api/fastapi/test_main.py`:
    - [x] success path with proxy stubbed response,
    - [x] auth/role rejection,
    - [x] payload validation errors,
    - [x] cache hit behavior,
    - [x] fallback/unavailable LanguageTool behavior.
  - [x] Frontend unit tests (`grammarUtils.test.ts`) for document text index and offset→ProseMirror range mapping (supports highlights + apply).
  - [x] Regression: grammar proxy does not touch DB (`test_grammar_proxy_does_not_touch_db`); grammar overlays use `view.setProps({decorations})` only (no extra doc transaction for paint).

## Dev Notes
### Story foundation and dependencies
- Epic 5 sequence indicates Story 5.5 builds on completed collaboration foundations: `5.1` (Hocuspocus/Yjs), `5.2` (secure WSS), `5.3` (audio-text sync), `5.4` (snapshot persistence).
- Story objective is already defined in `docs/epics-and-stories.md`: real-time grammar check using LanguageTool in editor context.

### Reuse-first guardrails (anti-reinvention)
- Reuse existing FastAPI auth patterns (`get_current_user`, role checks) and existing editor access semantics from Story 5.x.
- Reuse existing Redis service and conventions; do not introduce a second cache store.
- Reuse editor decoration-style approach from Story 5.3 for visual overlays; avoid document-mutation approach for highlighting.

### File structure requirements (expected touchpoints)
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `src/frontend/src/editor/TranscriptionEditor.tsx` (and closest editor helper modules)
- `src/frontend/src/editor/collaboration.css` (or existing editor styles)
- `src/compose.yml`
- `src/.env.example`
- `docs/api-mapping.md`
- `README.md`

### Contracts and data shape (proposed)
- Request:
  - `POST /v1/proxy/grammar`
  - Body: `{ "text": string, "language": string }`
- Response (normalized by FastAPI):
  - `{ "matches": [...], "degraded": bool }` — chaque match inclut `issueType` (`spelling` | `grammar`) pour le surlignage client.
- Error semantics:
  - `401/403` auth/role,
  - `422` payload invalid,
  - `429` fallback/rate-limit path,
  - `502/503` upstream unavailable (depending on current error taxonomy conventions).

### Testing requirements
- Validate debounce window behavior and cancellation/abort logic.
- Ensure deterministic behavior under concurrent collaboration updates.
- Validate cache key stability and TTL behavior in backend tests.
- Confirm no regression to existing `frontend-correction` submission flow and snapshot callback behavior.

### Assumptions (explicit, due missing planning artifacts)
- Dedicated PRD/architecture story decomposition artifacts for 5.5 were unavailable; requirements were synthesized from:
  - `docs/epics-and-stories.md` (story definition),
  - `docs/prd.md` §4.8 (LanguageTool behavior),
  - `docs/architecture.md` (proxy/cache/fallback expectations),
  - `docs/api-mapping.md` §7 (`POST /v1/proxy/grammar` contract).
- If product owner clarifies scope (e.g., multilingual spell dictionary, project-specific ignore list), update this story before `dev-story`.

### References
- [Source: docs/epics-and-stories.md#Epic 5 — Éditeur Collaboratif Souverain]
- [Source: docs/prd.md#4.8 Vérification Grammaticale (LanguageTool)]
- [Source: docs/architecture.md#1.C Couche Compute & Inférence (OpenVINO/LanguageTool)]
- [Source: docs/api-mapping.md#7. Proxy Grammaire]
- [Source: .bmad-outputs/implementation-artifacts/5-3-bidirectional-audio-text-sync.md]
- [Source: .bmad-outputs/implementation-artifacts/5-4-automatic-snapshot-persistence.md]

## Dev Agent Record
### Agent Model Used
Cursor agent (implementation) - 2026-03-31

### Debug Log References
- `py -m pytest test_main.py -q` in `src/api/fastapi` (154 passed)
- `npm test` and `npm run build` in `src/frontend`

### Completion Notes List
- Implemented `POST /v1/proxy/grammar`: JWT roles Transcripteur/Expert/Admin, validation, `httpx` → LanguageTool `/v2/check`, Redis cache `lt:grammar:<sha256>:<lang>`, 429 + regex locale espaces, 502/503 mapping, structured logs.
- Compose: service `languagetool` (erikvl87 image, port 8010, limits), FastAPI `depends_on` languagetool `service_healthy`; env `LANGUAGETOOL_URL`, `GRAMMAR_*` in compose + `.env.example`; README note.
- Editor: debounce 500ms, `grammarGenRef` anti-stale, merged decorations (grammar + karaoke), clic priorité grammaire puis seek audio, popup suggestions + `insertContentAt`, toggle **L**, statut non bloquant.
- Tests: `test_main.py` grammar suite + `grammarUtils.test.ts` (index doc / plages, apply guard, stale-gen contract) ; régression proxy sans `db.execute`.

### Code review remediation (patch follow-up)
- **Editor / mapping:** `buildDocTextIndex` inserts `\n` between text blocks; `docRangeForTextSlice` rejects slices overlapping block separators (no cross-block highlights). Grammar popup stores `expectedSlice`; `recomputeGrammarApplyRange` recomputes PM range at apply and aborts if index or live text diverges. On each document update (grammar on), generation bumps, matches clear, decorations repaint immediately before debounced fetch.
- **Backend:** `_normalize_lt_matches(matches, text)` prefers `rule.category` then top-level category; clamps invalid LT offsets/lengths to `len(text)`. Redis `SET … NX` fetch lock + short wait loop coalesces duplicate cache misses.
- **Compose:** LanguageTool healthcheck uses `wget --spider` on `/v2/languages`; FastAPI `depends_on` languagetool `service_healthy`.
- **Tests:** 401 missing `sub`, malformed offsets, clamp past EOF, rule-level category, fetch-lock NX on miss; extended `grammarUtils.test.ts` (paragraph boundaries, `recomputeGrammarApplyRange`, stale-gen contract).
- **Validation:** `py -m pytest test_main.py -q` (159 passed); `npm test` + `npm run build` in `src/frontend`.

### File List
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `src/frontend/src/editor/TranscriptionEditor.tsx`
- `src/frontend/src/editor/grammarUtils.ts`
- `src/frontend/src/editor/grammarUtils.test.ts`
- `src/frontend/src/editor/collaboration.css`
- `src/compose.yml`
- `src/.env.example`
- `docs/api-mapping.md`
- `README.md`
- `.bmad-outputs/implementation-artifacts/5-5-realtime-grammar-check-languagetool.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Change Log
- 2026-03-31: Story 5.5 implémentée — proxy LanguageTool, cache Redis, service compose, éditeur (décorations + suggestions), tests backend/frontend, docs.
- 2026-03-31: Correctifs revue de code — index par blocs + séparateurs, apply sûr, normalisation LT + verrou cache, healthcheck LT, tests supplémentaires.

## Traduction francaise (reference)
**Statut :** `review`

**Histoire :** En tant que Transcripteur, je veux voir les fautes d'orthographe/grammaire en temps reel dans l'editeur et appliquer rapidement des suggestions contextuelles, afin d'ameliorer la qualite linguistique sans casser le flux collaboratif.

**Points cles :**
1. Verification grammaticale debouncee (~500 ms) via `POST /v1/proxy/grammar`.
2. Proxy FastAPI securise (JWT + roles) vers LanguageTool avec cache Redis.
3. Surlignage visuel non destructif (decorations) et menu de correction contextuelle.
4. Fallback propre (429/5xx) sans bloquer l'edition.
5. Pas de regression CRDT, Golden Set, ni snapshots.
