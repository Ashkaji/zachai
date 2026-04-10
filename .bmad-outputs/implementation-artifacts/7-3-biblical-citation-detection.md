# Story 7.3: biblical-citation-detection

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created. -->

## Story
**As the** System,  
**I want** to detect biblical references in transcribed text and return structured citation positions,  
**so that** downstream systems can render, index, and analyze references reliably.

## Acceptance Criteria
1. **Endpoint contract**
   1. Given `POST /v1/nlp/detect-citations` is called with valid auth and payload,
   2. Then the API returns deterministic JSON: `{citations:[{reference,start_char,end_char}]}`,
   3. And each item is stable and machine-consumable for external integrations,
   4. And no-match cases return `200` with `{citations: []}`.

2. **Input validation and error semantics**
   1. Body contract is `{"text": "<string>"}` with non-empty text,
   2. Missing/invalid payload returns explicit 4xx responses,
   3. Very large payloads are bounded by explicit limits consistent with current FastAPI patterns.

3. **Detection quality baseline**
   1. Detector recognizes core `Book Chapter:Verse` forms (for example `John 3:16`, `Jn 3:16`, ranges like `Romans 8:28-30`),
   2. Returned offsets map to exact spans in source text (`start_char` inclusive, `end_char` exclusive),
   3. Offset indexes are computed against the original request text (normalization must not shift reported positions),
   4. False positives are reduced by deterministic normalization and boundary checks.

4. **Security and architecture guardrails**
   1. Route stays in FastAPI gateway and does not expose internal-only services,
   2. External access remains API-key protected as documented for open extensions endpoints,
   3. Logging remains privacy-safe (metadata, counts, timings; no unnecessary raw text leakage).

5. **Compatibility and scope boundaries**
   1. Story 7.3 must not regress Story 7.1 export routes and Story 7.2 transcribe route behavior,
   2. Initial scope is citation detection only (no translation, no RAG enrichment),
   3. Response remains minimal and stable: `reference`, `start_char`, `end_char`.

## Tasks / Subtasks
- [x] **Implement endpoint contract in FastAPI** (AC: 1, 2, 4)
  - [x] Add/confirm `POST /v1/nlp/detect-citations` route in `src/api/fastapi/main.py`.
  - [x] Enforce API key authentication path used for external open endpoints.
  - [x] Validate request body with explicit 4xx error semantics.

- [x] **Add deterministic citation extraction logic** (AC: 1, 3, 5)
  - [x] Create or reuse a dedicated parser utility module under FastAPI API code (avoid scattering regex in route handler).
  - [x] Normalize matched references to stable `reference` strings.
  - [x] Emit exact character offsets against original input text.
  - [x] Keep logic side-effect free and synchronous for predictable behavior.

- [x] **Harden edge cases and anti-false-positive checks** (AC: 2, 3)
  - [x] Reject empty/whitespace-only text.
  - [x] Handle punctuation, parentheses, and adjacent tokens without offset drift.
  - [x] Define deterministic handling for duplicates (preserve order of appearance, no hidden mutation).

- [x] **Extend tests and regression coverage** (AC: 1-5)
  - [x] Add tests in `src/api/fastapi/test_main.py` for:
    - [x] auth required / invalid key behavior,
    - [x] payload validation and size-limit boundaries,
    - [x] common citation patterns and range parsing,
    - [x] offset correctness on representative samples,
    - [x] no regressions for Story 7.1 and Story 7.2 routes.

- [x] **Update API docs mapping** (AC: 1, 2, 5)
  - [x] Update `docs/api-mapping.md` for final request/response/error semantics.
  - [x] Keep wording aligned with PRD Epic 7 extension intent.

### Review Findings
- [x] [Review][Patch] Undocumented `503` auth outcome for detect-citations [src/api/fastapi/main.py:1592]
- [x] [Review][Patch] Dotted abbreviations not detected (`Jn. 3:16`, `Rom. 8:28`) [src/api/fastapi/main.py:1924]
- [x] [Review][Patch] Semantically invalid verse ranges accepted (`John 3:16-14`) [src/api/fastapi/main.py:1937]

## Dev Notes
### Story foundation and dependencies
- Epic 7 goal is platform export/extensions; 7.3 extends the external API surface after 7.1 (exports) and 7.2 (open transcription).
- Business value: provide structured references to support downstream display/indexing without forcing external consumers to re-parse free text.

### Architecture compliance
- FastAPI remains the external gateway/control plane; keep endpoint implementation in `src/api/fastapi/main.py`.
- Do not introduce new public service exposure; internal compute services remain internal-only.
- Keep response contracts deterministic and minimal, matching established API style.

### Reuse-first guardrails (anti-reinvention)
- Reuse existing API key auth helpers and error envelope conventions from Story 7.2 implementation.
- Reuse existing test style and fixture patterns in `src/api/fastapi/test_main.py`.
- Prefer standard-library regex + small normalization map first; avoid unnecessary heavy NLP dependencies unless required by failing acceptance tests.

### Library/framework requirements
- Framework baseline: current FastAPI + Pydantic v2 request modeling and validation patterns.
- Detection strategy baseline: deterministic parser (regex/token normalization). If optional external parser is considered later, keep behind clear abstraction and avoid contract changes.

### File structure requirements (expected touchpoints)
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/7-3-biblical-citation-detection.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Testing requirements
- Validate auth and payload contracts explicitly (401/403/422 style consistency with existing external routes).
- Add table-driven cases for canonical references, abbreviations, ranges, and malformed near-matches.
- Assert exact offsets and deterministic output order.
- Add lightweight regression checks that Story 7.1/7.2 key routes still return expected semantics.

### Previous story intelligence (7.2)
- Story 7.2 established external API key guardrails, explicit validation, and deterministic response envelope patterns.
- Maintain conservative implementation with test-first hardening and clear scope boundaries.
- Keep docs and tests synchronized with endpoint contract to prevent drift.

### Git intelligence summary
- Recent commit history emphasizes validation/governance rigor and explicit workflow transitions.
- Maintain that pattern: concrete contracts, explicit failure modes, and exhaustive tests for edge cases.

### Latest technical information
- Current ecosystem supports specialized scripture parsers (`python-scriptures`, `pythonbible`, `bible-ref-parser`), but baseline for this story should remain deterministic and dependency-light unless coverage gaps demand otherwise.
- FastAPI/Pydantic v2 patterns favor explicit request models and strict validation for stable external APIs.

### Project context reference
- No dedicated `project-context.md` found.
- Authoritative sources used:
  - `docs/epics-and-stories.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/api-mapping.md`
  - `.bmad-outputs/implementation-artifacts/7-2-whisper-open-api.md`

### References
- [Source: docs/epics-and-stories.md#Epic 7 — Export & Extensions Plateforme]
- [Source: docs/prd.md#4.9 Export et Extensions]
- [Source: docs/prd.md#8. Plateforme d'Extensions]
- [Source: docs/api-mapping.md#8. Export & Extensions Plateforme]
- [Source: docs/architecture.md#1. Vue d'Ensemble — Couches Architecturales]
- [Source: docs/architecture.md#5. Sécurité (Zero Trust & Encryption)]
- [Source: .bmad-outputs/implementation-artifacts/7-2-whisper-open-api.md]

## Dev Agent Record
### Agent Model Used
Cursor agent (create-story) - 2026-04-01

### Debug Log References
- Story 7.3 selected from first backlog item in sprint status.
- Context consolidated from Epic 7 + PRD + architecture + API mapping + Story 7.2 implementation learnings.
- Route contract constrained to deterministic external API output for compatibility.
- Red phase: added 6 endpoint tests for auth, validation, match/no-match behavior, offsets, and ranges.
- Green phase: implemented `CitationDetectRequest`, citation parser helpers, and `POST /v1/nlp/detect-citations`.
- Added deterministic book alias normalization and stable offset extraction against original request text.
- Regression validation:
  - `pytest src/api/fastapi/test_main.py -k "detect_citations or whisper_transcribe" -q` (14 passed)
  - `pytest src/api/fastapi/test_main.py -q` (226 passed)

### Completion Notes List
- Story 7.3 context artifact prepared for `dev-story` implementation.
- Developer guardrails added for auth, deterministic parsing, offset correctness, and regression safety.
- Implemented external citation detection endpoint with API key authentication and strict body validation.
- Implemented deterministic parser supporting canonical forms, abbreviations, and verse ranges.
- Updated API mapping contract for error semantics, empty-result behavior, and offset definitions.
- Completed full FastAPI regression test suite with no failures.
- Applied code-review patch fixes for detect-citations (auth contract/docs, dotted abbreviation support, invalid range filtering).

### File List
- `.bmad-outputs/implementation-artifacts/7-3-biblical-citation-detection.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`

### Change Log
- 2026-04-01: Created Story 7.3 context (biblical citation detection), status set to `ready-for-dev`.
- 2026-04-01: Implemented Story 7.3 endpoint, parser logic, tests, and API mapping updates; status set to `review`.
- 2026-04-01: Addressed code review findings (3 patch items), revalidated tests, status set to `done`.

---

## Traduction francaise (reference)
**Statut :** `done`

**Histoire :** En tant que systeme, detecter les references bibliques dans un texte transcrit et renvoyer leurs positions structurees.

**Points cles :**
1. Endpoint `POST /v1/nlp/detect-citations` avec auth API key et contrat JSON deterministe.
2. Validation stricte du payload, semantique d'erreur explicite, limites de taille.
3. Detection fiable des formes `Livre Chapitre:Verset` avec offsets exacts.
4. Aucune regression des stories 7.1 et 7.2; perimetre limite a la detection.
