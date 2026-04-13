# Story 15.3: Ingestion, smoke tests et doc opérateur / Ingestion, smoke tests and operator docs

Status: in-progress

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As an Operator,
I want to run the Bible ingestion pipeline against the FastAPI backend, verify it with smoke tests, and have clear documentation on secrets and setup,
so that the team can repopulate the database after a reset or in a new environment.

## Traduction (FR)

**En tant qu'** opérateur, **je veux** exécuter la chaîne d'ingestion biblique vers le backend FastAPI, la vérifier avec des smoke tests et disposer d'une documentation claire sur les secrets et la configuration, **afin que** l'équipe puisse repeupler la base de données après une réinitialisation ou dans un nouvel environnement.

## Acceptance Criteria

1. **Given** the JSON files generated in Story 15.2,
   **When** `src/scripts/ingest_bible.py` is executed with the correct `--url` and `--secret`,
   **Then** it successfully populates the `bible_verses` table in PostgreSQL (verified by script output "Total successfully written").

2. **Given** a populated database,
   **When** a smoke test script queries `GET /v1/bible/verses` for "Golden Verses" (e.g., Jean 3:16, John 3:16),
   **Then** the API returns the correct text from the sovereign database with a 200 OK status.

3. **Given** the need for reproducibility,
   **When** an operator reads `docs/bible/README.md` (or a dedicated operator file),
   **Then** they find the exact commands for ingestion, the required environment variables (secrets), and the expected local file structure.

4. **Given** the internal security model,
   **When** ingestion is attempted without the `X-ZachAI-Golden-Set-Internal-Secret` header,
   **Then** the API returns a 403 Forbidden.

5. **Given** the Redis cache (Story 13.2),
   **When** re-ingestion occurs,
   **Then** the smoke test confirms that the cache is invalidated or updated (verified by querying the API and checking if the new text is returned).

## Tasks / Subtasks

- [x] **Task 1 — Operator Documentation (AC: #3)**
  - [x] Update `docs/bible/README.md` with "Operator Runbook" section.
  - [x] Document the use of `ingest_bible.py`.
  - [x] Define where to find/set `X-ZachAI-Golden-Set-Internal-Secret`.
  - [x] Document the `data/bible/json/` directory convention for converted files.

- [x] **Task 2 — Smoke Test Script (AC: #2, #5)**
  - [x] Create `src/scripts/smoke_test_bible.py`.
  - [x] Implement checks for `GET /v1/bible/verses` using a JWT (from a test user or admin).
  - [x] Verify both LSG and KJV "Golden Verses".
  - [ ] (Optional) Add a flag to verify Redis cache rotation if `BIBLE_VERSE_CACHE_ENABLED` is on.

- [ ] **Task 3 — End-to-End Validation (AC: #1, #4)**
  - [ ] Run a full ingest of the JSON files produced in 15.2.
  - [ ] Verify 403 response when using an invalid secret.
  - [ ] Confirm batching performance (e.g., 100 verses per batch).

## Dev Notes

### Technical Context & Guardrails

- **Authentication:** `POST /v1/bible/ingest` requires the header `X-ZachAI-Golden-Set-Internal-Secret`. This secret is shared with the Golden Set ingestion flow.
- **JWT for Smoke Test:** `GET /v1/bible/verses` requires a valid JWT. You can use `src/scripts/generate_test_token.py` (if it exists) or capture one from a logged-in session.
- **Portability:** Use `http://localhost:8000` as the default URL but ensure it's configurable via CLI arguments or environment variables.
- **Cache Invalidation:** The API automatically increments the `bible:verse:gen:{translation}` key in Redis upon successful ingestion. The smoke test should ideally confirm that a second request returns the latest data.

### Architecture Compliance

- **Sovereignty:** This completes the "No live API" requirement (FR27).
- **Security:** Ensure the internal secret is NOT committed to the repo. It should be passed as an argument or environment variable.

### Project Structure Notes

- **Scripts:** All operational scripts should remain in `src/scripts/`.
- **Docs:** Operator instructions should be integrated into `docs/bible/` to keep Bible-related knowledge centralized.

### References

- **API Implementation:** `src/api/fastapi/main.py` §5551+ (Bible Engine).
- **Ingest Script:** `src/scripts/ingest_bible.py`.
- **Validation Logic:** `src/scripts/validate_bible_json.py` (has Golden Verse definitions).
- **Bible Docs:** `docs/bible/README.md`, `docs/bible/SOURCES.md`, `docs/api-mapping.md` §17.

## Dev Agent Record

### Agent Model Used

Gemini 2.0 Flash (bmad-create-story workflow)

### Debug Log References

- N/A

### Completion Notes List

- N/A

### File List

- `docs/bible/README.md` (modified)
- `src/scripts/smoke_test_bible.py` (new)
- `.bmad-outputs/implementation-artifacts/15-3-bible-ingest-smoke-and-operator-docs.md` (this file)

### Review Findings

- [x] [Review][Patch] Operator README overclaims cache verification — **Addressed:** README now describes GET/snippet checks and explains Redis generation bump without claiming the script validates cache internals.
- [x] [Review][Patch] Smoke test exit code allows partial success — **Addressed:** script returns failure unless all golden verses pass.
- [x] [Review][Patch] 404 treated as SKIP — **Addressed:** 404 is a hard FAIL; messaging updated.
- [x] [Review][Patch] Operator runbook missing ingest auth checks — **Addressed:** `curl` examples for missing header (401) and wrong secret (403), matching `main.py` behavior.
- [x] [Review][Patch] Fragile JSON shape handling — **Addressed:** verse text read via `dict` + `.get("text", "")`.
