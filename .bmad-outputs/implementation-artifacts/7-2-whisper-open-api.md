# Story 7.2: whisper-open-api

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created. -->

## Story
**As an** API Consumer,  
**I want** to send an audio file to `POST /v1/whisper/transcribe` and receive a timestamped JSON transcription,  
**so that** external systems can leverage ZachAI's fine-tuned Whisper model.

## Acceptance Criteria
1. **Open API endpoint contract**
   1. Given `POST /v1/whisper/transcribe` is called,
   2. Then endpoint uses API key auth via header `Authorization: Bearer <api_key>`,
   3. And missing/invalid API key returns explicit auth errors (`401` for missing/invalid, `403` for revoked/forbidden key),
   4. And returns a structured JSON transcription payload with timestamped segments.

2. **Input modes and validation**
   1. Request uses canonical external input contract: JSON body with `audio_url` (required) and `language` (optional),
   2. Invalid/missing input produces explicit 4xx semantics,
   3. Unsafe or unsupported URL/format conditions are rejected deterministically,
   4. File-upload multipart mode is out of scope for Story 7.2 (URL ingestion only).

3. **Inference integration and output shape**
   1. Endpoint orchestrates existing pipeline components (FastAPI orchestration + OpenVINO/Whisper),
   2. Response includes stable segment schema (e.g., `[{start, end, text, confidence}]`),
   3. Response is deterministic and machine-consumable for downstream integrations,
   4. Response includes stable top-level envelope fields: `segments`, `language_detected` (if available), `model_version` (if available), `duration_s` (if available).

4. **Security and tenant isolation guardrails**
   1. Internal services remain internal-only (no direct exposure of OpenVINO/worker internals),
   2. API key auth and request controls prevent anonymous abuse,
   3. Request handling prevents SSRF-style fetch abuse and disallows private-network targets,
   4. SSRF blocklist includes localhost/loopback, link-local, RFC1918 private ranges, and cloud metadata endpoints.

5. **Performance and resilience behavior**
   1. Timeouts/failures from upstream workers are mapped to explicit 5xx contracts,
   2. Logging is structured and privacy-safe (metadata only),
   3. Endpoint behavior is observable and consistent with existing FastAPI error style,
   4. Operational constraints are explicit and enforced: max audio URL fetch size, max accepted duration, and upstream timeout budget.

6. **Story boundary and compatibility**
   1. Story 7.2 must not regress Story 7.1 export routes,
   2. Must not overlap Story 7.3 citation detection scope,
   3. Existing internal transcription workflows (manager/transcripteur lifecycle) remain unchanged,
   4. Canonical method for this endpoint is `POST` (PRD legacy `GET` mention is treated as outdated and not implemented).

## Tasks / Subtasks
- [x] **Define external API auth + route contract** (AC: 1, 2, 4)
  - [x] Implement/confirm `POST /v1/whisper/transcribe` in `src/api/fastapi/main.py`.
  - [x] Add API key authentication contract for external consumers (separate from JWT role paths) using `Authorization: Bearer <api_key>`.
  - [x] Validate request schema (`audio_url`, optional `language`) with explicit error responses.
  - [x] Document canonical method decision (`POST` only).

- [x] **Implement secure input handling** (AC: 2, 4)
  - [x] Validate URL scheme and reject unsupported/non-http(s) inputs.
  - [x] Block private-network/loopback/link-local/metadata targets to reduce SSRF exposure.
  - [x] Enforce predictable constraints (max fetch size, accepted duration ceiling, upstream timeout budget) in request path.

- [x] **Integrate inference orchestration** (AC: 3, 5)
  - [x] Reuse existing OpenVINO/Whisper integration patterns (no duplicate inference stack).
  - [x] Map inference output to stable response schema `{segments:[{start,end,text,confidence}], language_detected?, model_version?, duration_s?}`.
  - [x] Handle upstream failures with clear 502/503 style semantics.

- [x] **Harden observability and error contracts** (AC: 5, 6)
  - [x] Emit structured logs for request lifecycle without sensitive payload leakage.
  - [x] Preserve existing API error envelope consistency (`detail.error` style).
  - [x] Ensure no regressions on Story 7.1 endpoints/contracts.

- [x] **Extend backend tests (red-green-refactor)** (AC: 1-6)
  - [x] Add tests in `src/api/fastapi/test_main.py` for:
    - [x] auth required / invalid key / valid key success,
    - [x] input validation failures,
    - [x] SSRF/private-network URL rejection,
    - [x] method guard behavior (`POST` allowed, `GET` not implemented for this route),
    - [x] limits validation (size/duration/timeout contract),
    - [x] upstream error mapping,
    - [x] successful deterministic payload shape.

- [x] **Update API documentation** (AC: 1, 2, 3, 5)
  - [x] Update `docs/api-mapping.md` for `/v1/whisper/transcribe` auth/body/response/errors.
  - [x] Keep wording aligned with PRD and Epic 7 scope boundaries.

## Dev Notes
### Story foundation and dependencies
- Epic 7 progression: `7.1 exports` completed, `7.2 open API` next.
- Business intent: expose controlled external transcription capability while preserving sovereign internal architecture.

### Architecture compliance
- FastAPI remains orchestration/control plane.
- OpenVINO/Whisper remains internal compute service.
- Do not expose internal worker endpoints directly; keep gateway mediation.

### Reuse-first guardrails (anti-reinvention)
- Reuse existing authentication/error/logging patterns in `src/api/fastapi/main.py`.
- Reuse current inference service patterns rather than introducing alternate model-serving stack.
- Avoid new dependencies unless strictly required by implementation constraints.

### File structure requirements (expected touchpoints)
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/7-2-whisper-open-api.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Testing requirements
- Tests should validate auth, input safety, and response shape determinism.
- Include failure-path tests for upstream timeouts/errors.
- Ensure Story 7.1 route behavior remains intact.

### Previous story intelligence (7.1)
- 7.1 strengthened deterministic contracts (`audio_id`, strict status/error semantics, direct stream outputs).
- 7.2 should preserve same rigor: explicit contracts and defensive edge-case handling.

### Git intelligence summary
- Recent patterns emphasize lifecycle correctness, explicit API semantics, and edge-case test completeness.
- Keep implementation conservative and test-backed.

### Latest technical information
- PRD/API references show external endpoint intent with API-key style contract.
- Current architecture positions FastAPI as the only external gateway to internal inference services.
- Method discrepancy identified in legacy PRD text (`GET`) vs current contract (`POST`); Story 7.2 standardizes on `POST`.

### Project context reference
- No `project-context.md` found in repository.
- Authoritative references:
  - `docs/epics-and-stories.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/api-mapping.md`
  - `.bmad-outputs/implementation-artifacts/7-1-export-docx-txt-srt.md`

### References
- [Source: docs/epics-and-stories.md#Epic 7 — Export & Extensions Plateforme]
- [Source: docs/prd.md#4.9 Export et Extensions]
- [Source: docs/architecture.md#1. Vue d'Ensemble — Couches Architecturales]
- [Source: docs/architecture.md#5. Sécurité (Zero Trust & Encryption)]
- [Source: docs/api-mapping.md#8. Export & Extensions Plateforme]
- [Source: .bmad-outputs/implementation-artifacts/7-1-export-docx-txt-srt.md]

## Dev Agent Record
### Agent Model Used
Cursor agent (create-story) - 2026-04-01

### Debug Log References
- Story 7.2 auto-selected from first backlog item in sprint status.
- Context consolidated from Epic 7 + PRD + architecture + recent story patterns.
- Implemented `POST /v1/whisper/transcribe` with external API key verification.
- Added URL security guards against SSRF/private-network targets and strict WAV ingestion contract.
- Integrated FastAPI orchestration with OpenVINO worker `/transcribe` contract via MinIO staging.
- Added Story 7.2 test coverage for auth, validation, SSRF rejection, upstream error mapping, and successful response shape.
- Test evidence:
  - `pytest src/api/fastapi/test_main.py -k "whisper_transcribe or transcribe" -q` (9 passed)
  - `pytest src/api/fastapi/test_main.py -q` (220 passed)

### Completion Notes List
- Story 7.2 context artifact prepared for `dev-story` implementation.
- Security and API-contract guardrails emphasized for external-facing endpoint.
- External transcription endpoint now available with API key auth and deterministic output envelope.
- Defensive URL/network checks and timeout/error mappings are implemented for open API safety.

### File List
- `.bmad-outputs/implementation-artifacts/7-2-whisper-open-api.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`

### Change Log
- 2026-04-01: Created Story 7.2 context (open Whisper API), status set to `ready-for-dev`.
- 2026-04-01: Implemented Story 7.2 open API endpoint, added backend tests and API docs updates; status moved to `review`.
- 2026-04-01: Applied review fixes (OpenVINO 400->422 mapping, MinIO staged-object cleanup, GET method guard test); status moved to `done`.

---

## Traduction francaise (reference)
**Statut :** `ready-for-dev`

**Histoire :** En tant que consommateur API, je veux appeler `POST /v1/whisper/transcribe` pour obtenir une transcription horodatee exploitable en JSON.

**Points cles :**
1. Auth externe par cle API avec contrat strict.
2. Validation d'entree + protections SSRF/reseau prive.
3. Reutilisation de la chaine d'inference existante (pas de pile parallele).
4. Reponses deterministes et tests d'erreurs upstream complets.
