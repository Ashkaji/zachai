# Story 7.1: export-docx-txt-srt

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created. -->

## Story
**As a** Transcripteur,  
**I want** to export a validated transcription as `.docx`, `.txt`, or `.srt`,  
**so that** the content is ready for editorial workflows and subtitle deployment.

## Acceptance Criteria
1. **Export eligibility and RBAC**
   1. Given an export request for an audio/transcription,
   2. Then only authenticated users with project access can export,
   3. And export is allowed only when `AudioFile.status = validated` (no alternate approved states in this story),
   4. And unauthorized/ineligible requests return explicit API errors (`401` unauthenticated, `403` forbidden, `404` not found in caller scope, `409` invalid lifecycle state).

2. **TXT export**
   1. Given a validated transcription,
   2. Then system can generate plain UTF-8 `.txt` content from normalized final text,
   3. And response contract supports deterministic download semantics (filename, mime type, bytes/stream).

3. **SRT export from inline timestamps**
   1. Given timestamped transcription segments,
   2. Then system can generate `.srt` with sequential cues and valid SRT time format,
   3. And cue ordering preserves timeline integrity,
   4. And malformed/missing timestamp data returns `422` with explicit validation detail,
   5. And cues with non-positive duration or descending timestamps are rejected with `422`,
   6. And SRT times are emitted as `HH:MM:SS,mmm` using deterministic millisecond rounding.

4. **DOCX export integration**
   1. Given a validated transcription,
   2. Then system can generate `.docx` output through the existing export path (Export Worker integration pattern),
   3. And API response contract is deterministic: direct file stream with download headers (no presigned URL mode in Story 7.1),
   4. And generated document contains expected textual content without breaking current snapshot/export behavior.

5. **File naming and storage/streaming consistency**
   1. Export filenames are deterministic and project-safe (no traversal/unsafe chars),
   2. Export flow aligns with MinIO/export-worker conventions already used by snapshots,
   3. And no duplicate ad-hoc storage path is introduced.

6. **API contract and documentation**
   1. API mapping includes endpoint/auth/query/body/error contracts for export formats,
   2. Including `GET /v1/export/subtitle/{audio_id}?format=srt` behavior from PRD scope,
   3. Including `GET /v1/export/transcript/{audio_id}?format=txt|docx` for transcript exports,
   4. And route identifiers are canonicalized on `audio_id` for Story 7.1 endpoints and tests,
   5. And accepted format values are explicitly enumerated (`txt`, `srt`, `docx`) with invalid format returning `422`,
   6. And story explicitly keeps out-of-scope features (new formats, open API extensions in 7.2, citation NLP in 7.3).

7. **Regression and quality guardrails**
   1. Existing collaboration/snapshot flows remain unchanged,
   2. Existing validation lifecycle semantics from Epic 6 remain intact,
   3. Automated tests cover happy path plus auth/state/format edge cases.

## Tasks / Subtasks
- [x] **Define export service contract and route entrypoints** (AC: 1, 6)
  - [x] Confirm canonical export endpoints and request/response contracts in `src/api/fastapi/main.py` using `audio_id` as the route identifier:
        - `GET /v1/export/subtitle/{audio_id}?format=srt`
        - `GET /v1/export/transcript/{audio_id}?format=txt|docx`
  - [x] Reuse existing auth/project-membership checks and consistent error envelope.
  - [x] Document accepted format values (`txt`, `srt`, `docx`) and explicit out-of-scope behavior.
  - [x] Fix status/error semantics in API mapping: `401`, `403`, `404`, `409`, `422`.

- [x] **Implement TXT export path** (AC: 2, 5)
  - [x] Build plain text formatter from final transcription source-of-truth.
  - [x] Return deterministic filename + content type (`text/plain`) with download headers.
  - [x] Validate unicode/line-break handling and normalize final output.

- [x] **Implement SRT export path** (AC: 3, 5, 6)
  - [x] Build SRT cue generator from inline timestamps/segment model.
  - [x] Enforce strict cue numbering and `HH:MM:SS,mmm` timing format.
  - [x] Reject missing/invalid/descending/non-positive timestamp segments with `422`.
  - [x] Align with PRD subtitle endpoint shape (`/v1/export/subtitle/{audio_id}?format=srt`).

- [x] **Integrate DOCX export without reinvention** (AC: 4, 5)
  - [x] Reuse existing Export Worker conversion pattern used for snapshot DOCX/JSON.
  - [x] Avoid introducing parallel DOCX generation libraries in FastAPI when worker path already exists.
  - [x] Ensure generated DOCX payload remains compatible with current MinIO/export conventions.
  - [x] Lock one deterministic delivery mode (stream or presigned URL) and test it.

- [x] **Harden security and file safety** (AC: 1, 5, 7)
  - [x] Sanitize export filenames and prevent path traversal/injection.
  - [x] Keep role and project scoping checks mandatory on each export route.
  - [x] Preserve internal-only service boundaries (no public exposure of internal worker-only components).

- [x] **Extend tests (red-green-refactor)** (AC: 1-7)
  - [x] Add tests in `src/api/fastapi/test_main.py` for auth/project-access checks.
  - [x] Add TXT/SRT successful export tests and content contract assertions.
  - [x] Add failure tests: invalid format, non-validated status, missing timestamps, unknown resource.
  - [x] Add DOCX path integration tests using mocks/stubs aligned to existing worker contracts.

- [x] **Update documentation and operational notes** (AC: 6, 7)
  - [x] Update `docs/api-mapping.md` with endpoint contracts, mime types, and status/error semantics.
  - [x] Add or update export notes in docs where needed without conflicting with story 7.2/7.3 scopes.

## Dev Notes
### Story foundation and dependencies
- Story anchor: Epic 7 export enablement for publishable outputs (`.docx`, `.txt`, `.srt`).
- Dependency chain:
  - Epic 5 established timestamped collaborative document foundations.
  - Epic 6 established validation lifecycle gate; Story 7.1 should export only from validated outputs.
- Story boundaries:
  - 7.1 = export formats and contracts,
  - 7.2 = open Whisper API,
  - 7.3 = biblical citation detection.

### Architecture compliance
- Reuse existing layered architecture: FastAPI gateway/orchestration, Export Worker for conversion tasks, MinIO for object storage, PostgreSQL as truth.
- Keep internal-service isolation intact (Export Worker and internal compute components stay internal network only).
- Maintain existing checksum/robustness discipline on export-worker-integrated flows where applicable.

### Reuse-first guardrails (anti-reinvention)
- Reuse existing export-worker patterns and wiring already present for snapshot DOCX/JSON generation.
- Reuse existing API auth/RBAC/project-membership guard utilities and error semantics.
- Do not introduce new storage systems, queue stacks, or duplicate conversion pipelines for this story.

### File structure requirements (expected touchpoints)
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `src/export-worker/*` (if route integration requires worker-side extension)
- `.bmad-outputs/implementation-artifacts/7-1-export-docx-txt-srt.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Testing requirements
- Keep tests deterministic and mock-driven.
- Cover:
  - authorization and project scoping,
  - status eligibility (`validated` gate),
  - format correctness (`txt`, `srt`, `docx`),
  - SRT timing/cue ordering edge cases,
  - invalid input and missing resource semantics.
- Preserve regression safety for snapshot export and Epic 6 validation workflows.

### Previous story intelligence
- No previous story in Epic 7 (`7.1` is first), so cross-story implementation learnings are taken from completed Epic 6 and export-related architecture/PRD sections.

### Git intelligence summary
- Recent commits show a pattern of strict lifecycle guardrails, explicit status transitions, and broad edge-case test coverage.
- Follow the same quality bar: explicit 4xx/403/404 semantics, no hidden side effects, and clear API mapping updates.

### Latest technical information
- Keep stack alignment with current architecture and PRD:
  - FastAPI gateway for contracts,
  - Export Worker (Node.js) for conversion-oriented export tasks,
  - MinIO-compatible artifact handling,
  - subtitle export endpoint contract in PRD (`format=srt`).
- Do not add speculative dependencies unless implementation proves a real gap in existing worker capabilities.

### Project context reference
- No `project-context.md` found in repository.
- Authoritative references:
  - `docs/epics-and-stories.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/ux-design.md`
  - `.bmad-outputs/implementation-artifacts/6-3-project-closure-golden-set-archival.md`
  - `.bmad-outputs/implementation-artifacts/6-2-manager-approval-rejection.md`

### References
- [Source: docs/epics-and-stories.md#Epic 7 — Export & Extensions Plateforme]
- [Source: docs/prd.md#4.9 Export et Extensions]
- [Source: docs/architecture.md#1. Vue d'Ensemble — Couches Architecturales]
- [Source: docs/architecture.md#6. Docker Compose — Ordre de Démarrage]
- [Source: docs/ux-design.md#7. User Journeys]
- [Source: .bmad-outputs/implementation-artifacts/6-3-project-closure-golden-set-archival.md]
- [Source: .bmad-outputs/implementation-artifacts/6-2-manager-approval-rejection.md]

## Dev Agent Record
### Agent Model Used
Cursor agent (create-story) - 2026-04-01

### Debug Log References
- Story context assembled from epics/architecture/PRD/UX and recent implementation artifacts.
- Sprint tracking updated to move story `7-1-export-docx-txt-srt` to `ready-for-dev`.
- Implemented export endpoints:
  - `GET /v1/export/subtitle/{audio_id}?format=srt`
  - `GET /v1/export/transcript/{audio_id}?format=txt|docx`
- Added validated-status gate, canonical `audio_id` routing, deterministic filename sanitization, and explicit `422` format/timestamp validation.
- Added deterministic SRT generator (`HH:MM:SS,mmm`) and minimal DOCX stream generation.
- Test evidence:
  - `pytest src/api/fastapi/test_main.py -k "export_subtitle or export_transcript" -q` (6 passed)
  - `pytest src/api/fastapi/test_main.py -q` (209 passed)

### Completion Notes List
- Story 7.1 context artifact prepared for `dev-story` implementation.
- Export format guardrails, architecture constraints, and anti-reinvention patterns are explicitly defined.
- Scope boundaries with stories 7.2 and 7.3 are explicit to prevent spillover.
- Export API contracts now match hardened story and API mapping with explicit role/status/error semantics.
- Added TXT/SRT/DOCX export implementation and Story 7.1 regression-focused test coverage.

### File List
- `.bmad-outputs/implementation-artifacts/7-1-export-docx-txt-srt.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`

### Change Log
- 2026-04-01: Created Story 7.1 context with comprehensive export guardrails and implementation guidance; status set to `ready-for-dev`.
- 2026-04-01: Implemented Story 7.1 export endpoints (TXT/SRT/DOCX), added tests, aligned API mapping, and moved status to `review`.

---

## Traduction francaise (reference)
**Statut :** `ready-for-dev`

**Histoire :** En tant que Transcripteur, je veux exporter une transcription validee en `.docx`, `.txt` ou `.srt`, afin de preparer rapidement des livrables editoriaux et des sous-titres.

**Points cles :**
1. Controle RBAC + appartenance projet et gate de cycle de vie `validated`.
2. Export `.txt` deterministic (UTF-8) et `.srt` conforme (cues ordonnes + format temps strict).
3. Reutilisation prioritaire du Export Worker pour `.docx` (pas de reimplementation parallele).
4. Documentation API explicite + non-regression des flux snapshots et validation Epic 6.
