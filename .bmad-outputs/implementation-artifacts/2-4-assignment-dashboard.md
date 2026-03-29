# Story 2.4: Assignment Dashboard (Manager + Transcripteur)

Status: done

<!-- Note: Validation is optional. Run `bmad-create-story` → Validate Story before `bmad-dev-story`. -->

## Story

As a **Manager**,  
I want to see all audios in my projects with assignee and processing status, and assign or reassign work to transcripteurs,  
so that I can track progress and route audio files efficiently.

As a **Transcripteur**,  
I want a consolidated list of audio tasks assigned to me with their status,  
so that I know what to work on next.

*[Sources: docs/epics-and-stories.md § Epic 2 Story 2.4; docs/prd.md §4.1; docs/api-mapping.md §2–3]*

---

## Acceptance Criteria

1. **`AudioFile` lifecycle vs PRD (blocking)**  
   PRD §3.1 / §4.5 define `uploaded → assigned → in_progress → transcribed → validated` for **human** workflow. Story 2.3 currently sets `AudioFileStatus.TRANSCRIBED` after **FFmpeg** success, which collides with “transcripteur soumis” semantics.  
   - **Refactor:** After successful normalization, the row must **not** use `transcribed` for “FFmpeg done”. Recommended approach: on FFmpeg **success**, keep `status = uploaded` with `normalized_path` populated (and `validation_error` null); use `in_progress` only while the FFmpeg request is in flight (short window) **or** introduce a dedicated enum value (e.g. `normalized`) if you prefer explicit states—**pick one approach**, document the mapping in Dev Notes, and **update Story 2.3 tests** that assert `transcribed` after register/normalize.  
   - **Dashboard rule:** Manager may assign only audios that are **eligible** (normalized successfully: `normalized_path` not null, no blocking validation error—align with product wording in UI).

2. **`Assignment` persistence (architecture)**  
   Implement the `Assignment` entity per [docs/architecture.md §3. Modèle de Données Métier] (PostgreSQL): link `audio_id` → single active assignment row (unique per `audio_id`); store `transcripteur_id` as Keycloak **`sub`** (string, same pattern as `Project.manager_id`). Timestamps: at least `assigned_at`; leave `submitted_at` / `manager_validated_at` nullable for Epic 6 unless you implement stub columns now.  
   - On successful assign/reassign: set `AudioFile.status` to **`assigned`** (from `uploaded` / `assigned` reassign).  
   - **403** if Manager is not project owner (`project.manager_id == token sub`) unless **Admin**.

3. **`GET /v1/projects/{project_id}/status` (api-mapping)**  
   - **Auth:** Manager (project owner) or **Admin**.  
   - **404** if project missing. **403** if caller is Manager but not this project’s `manager_id`.  
   - **Response shape** (minimum): `{ "project_status": "<draft|active|completed>", "audios": [ { "id", "filename", "status", "normalized_path" | null, "validation_error" | null, "assigned_to": "<sub>|null", "assigned_at": "<iso>|null" } ] }` — extend with fields needed by the frontend (e.g. `duration_s`) without breaking existing clients; use consistent naming with `_audio_file_to_dict` where possible.

4. **`POST /v1/projects/{project_id}/assign` (api-mapping)**  
   - **Auth:** Manager (owner) or Admin.  
   - **Body:** `{ "audio_id": int, "transcripteur_id": str }` (`transcripteur_id` = Keycloak `sub` of a Transcripteur). **MVP:** trust Manager-supplied `sub`; document follow-up (Keycloak Admin validation).  
   - **404** unknown project/audio or audio not in project. **400** if audio not assignable (not normalized per AC1). **409** optional if you disallow assign while `in_progress` / `transcribed` / `validated`—state rules must be documented and tested.  
   - Upsert assignment row; update `AudioFile.status` to `assigned`.

5. **Transcripteur task list**  
   **New** endpoint (not spelled in api-mapping—add to Dev Notes and `docs/api-mapping.md` in same PR if project convention is to keep mapping current): e.g. `GET /v1/me/audio-tasks` or `GET /v1/transcripteur/audio-tasks`.  
   - **Auth:** role **Transcripteur** (and optionally **Admin** for debug—your call; if Admin, document).  
   - Returns list of audios **assigned to** caller’s `sub`, across projects: each item includes at least `audio_id`, `project_id`, `project_name`, `filename`, `status`, `assigned_at`.  
   - **403** for non-Transcripteur (unless you allow Admin).

6. **Manager “all projects” overview (PRD §4.1)**  
   Either extend existing `GET /v1/projects` with optional query `?include=audio_summary` **or** add `GET /v1/dashboard/manager/summary` returning per-project `{ id, name, status, audio_counts_by_status..., unassigned_normalized_count }`. Choose one; **avoid N+1** DB patterns (prefer aggregate queries or bounded joins).

7. **Validation / reject (PRD Manager actions)**  
   Epic **6.2** owns full manager approval flow. For **2.4**, either:  
   - **Defer:** document that “validate/reject” buttons wire to Epic 6 endpoints when available; **no** placeholder routes, **or**  
   - Implement **thin** `POST /v1/transcriptions/{audio_id}/validate` per [docs/api-mapping.md §3] only if it stays minimal (status + optional comment) without duplicating full Epic 6 notifications—if so, reference Story 6.2 and keep scope tight.

8. **Testing**  
   - New tests in `src/api/fastapi/test_main.py`: assign happy path, forbidden assign (not normalized), role enforcement (Manager not owner, Transcripteur calling manager endpoints), transcripteur task list, project status payload shape, **plus** updated assertions for refactored post-FFmpeg status (AC1).  
   - Preserve green suite after AC1 refactor (adjust existing 2.3 tests).  
   - Target **≥ 8** new/changed tests minimum.

9. **Docs**  
   If new routes are added, update `docs/api-mapping.md` in the same change set.

---

## Tasks / Subtasks

- [x] **Task 1** — State machine alignment (AC: 1, 8)  
  - [x] Change `call_ffmpeg_normalize` success path per AC1; list all call sites of `AudioFileStatus.TRANSCRIBED`.  
  - [x] Update tests that expect `transcribed` after normalize.

- [x] **Task 2** — ORM & DDL (AC: 2)  
  - [x] Add `Assignment` model + relationship from `AudioFile`.  
  - [x] Alembic/migration or documented DDL for brownfield Postgres (match Story 2.3 Dev Notes style).

- [x] **Task 3** — `GET .../status` (AC: 3)  
  - [x] Implement route; reuse session/`selectin` patterns from existing project routes.

- [x] **Task 4** — `POST .../assign` (AC: 4)  
  - [x] Pydantic request/response models; transaction boundaries (assignment + audio status).

- [x] **Task 5** — Transcripteur list (AC: 5)  
  - [x] Query assignments joined to `AudioFile` + `Project` for `transcripteur_id == sub`.

- [x] **Task 6** — Manager overview (AC: 6)  
  - [x] Extend list or new summary endpoint; document choice in Dev Notes.

- [x] **Task 7** — Validate/reject scope (AC: 7)  
  - [x] Explicitly commit to defer **or** implement thin validate endpoint; update story Completion Notes.

- [x] **Task 8** — Docs & compose (AC: 9)  
  - [x] api-mapping; `.env` only if new vars (ideally none).

### Review Findings

- [x] [Review][Patch] Support Admin debug scope on `GET /v1/me/audio-tasks` via optional `?transcripteur_id=` query while keeping Transcripteur self-scope by token `sub` [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Handle assignment upsert race with explicit conflict response (catch `IntegrityError` on first-time concurrent assign and return 409) [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Add test coverage for 409 when assigning a `validated` audio status (AC4 optional-409 path is documented for `transcribed|validated`) [`src/api/fastapi/test_main.py`]
- [x] [Review][Patch] Add owner-manager happy-path test for `GET /v1/projects/{project_id}/status` (AC3) [`src/api/fastapi/test_main.py`]
- [x] [Review][Patch] Add test for 404 when `audio_id` exists but is not in `{project_id}` on assign (AC4) [`src/api/fastapi/test_main.py`]
- [x] [Review][Patch] Align API docs for `POST /v1/projects` auth with implementation (`Manager or Admin`) [`docs/api-mapping.md`]
- [x] [Review][Patch] Update sprint summary comment removing stale “Next: dev-story 2.4” now that story is in review [`\.bmad-outputs/implementation-artifacts/sprint-status.yaml`]
- [x] [Review][Defer] Cross-manager project status mutation remains possible on legacy `PUT /v1/projects/{project_id}/status` [`src/api/fastapi/main.py`] — deferred, pre-existing
- [x] [Review][Defer] 403 message for missing JWT `sub` on owner checks should ideally be 401/clear token-shape error [`src/api/fastapi/main.py`] — deferred, pre-existing

---

## Dev Notes

### Architecture compliance

- JWT + RBAC before all mutations; flat `{"error": "..."}` errors ([Source: docs/architecture.md §5]).  
- No audio binaries through FastAPI; dashboard is **metadata only**.  
- Compose stack unchanged unless new service (not expected).

### Project structure & files

- Primary: `src/api/fastapi/main.py` (models, routes, deps).  
- Tests: `src/api/fastapi/test_main.py`.  
- Optional: migrate large routers later—out of scope unless file already splitting.

### UX (Azure Flow)

- Dashboard **Manager**: table/list with status coloring; align with [docs/ux-design.md]: validation green `#28A745` / `#34D399` for validated states when present; primary actions blue. **Real-time** in PRD: **MVP = polling** (no WebSocket in this story; Epic 5 covers realtime editor).

### References

- [docs/epics-and-stories.md](docs/epics-and-stories.md) — Epic 2, Story 2.4  
- [docs/prd.md §4.1](docs/prd.md) — Dashboard fonctionnel  
- [docs/api-mapping.md](docs/api-mapping.md) — §2 Projets, §3 Gouvernance (future)  
- [docs/architecture.md §3](docs/architecture.md) — `Assignment` block diagram  
- Previous story: [.bmad-outputs/implementation-artifacts/2-3-audio-upload-ffmpeg-normalization.md](.bmad-outputs/implementation-artifacts/2-3-audio-upload-ffmpeg-normalization.md)

---

## Developer Context: Code Patterns & Integration Points

### Auth & roles

- `get_roles(payload)`, `decode_token`; Manager/Admin/Transcripteur checks mirror Story 2.2/2.3 `audio-files` routes.  
- Project ownership: `Project.manager_id` vs `payload["sub"]`.

### Existing audio APIs

- `GET/POST .../audio-files/*` from Story 2.3; `_audio_file_to_dict`, `AudioFileStatus` enum—**will change semantics** per AC1.

---

## Previous Story Intelligence (2.3)

- FFmpeg success currently sets **`transcribed`** — **must be reconciled** in this story (AC1).  
- `validation_error` / `validation_attempted_at` / `normalized_path` already model normalization outcome; use them for assignability.  
- Tests use `make_mock_project`, `dependency_overrides[get_db]`, patched MinIO/FFmpeg HTTP—extend similarly.  
- Review notes: legacy `POST /v1/upload/request-put` remains; out of scope for 2.4.

---

## Git Intelligence Summary

Recent commits emphasize Story 2.3 story authoring and 2.2 patches; **implement 2.4 in a new commit** after this story file—verify live `main.py` matches 2.3 story Dev Notes before coding.

---

## Latest Technical Notes

- Prefer **SQLAlchemy 2.0** async patterns already in `main.py`.  
- Keycloak user directory: MVP assigns by `sub`; documenting `preferred_username` in API responses requires userinfo or Admin API—**optional** enhancement.

---

## Project Context Reference

- No `project-context.md` in repo root; use `docs/architecture.md` + `docs/prd.md` + prior story files as brownfield context.

---

## Story Completion Status (BMad create-story)

**Generated:** 2026-03-29  
**Context engine:** Full `sprint-status.yaml` order scan; `docs/epics-and-stories.md`; PRD §4.1; architecture §3; api-mapping §2–3; `main.py` ORM/route inventory; Story 2.3 file.  
**Status:** review  
**Note:** `planning_artifacts/*epic*` glob was empty—epics loaded from `docs/epics-and-stories.md` (project convention).

---

## Traduction (FR) — résumé

- **Objectif :** tableau de bord d’assignation : le Manager voit les audios et assigne des transcripteurs ; le Transcripteur voit ses tâches.  
- **Point clé :** corriger la sémantique du statut après FFmpeg (ne pas utiliser `transcribed` pour la normalisation).  
- **API :** `GET /v1/projects/{id}/status`, `POST /v1/projects/{id}/assign`, liste des tâches transcripteur ; résumé multi-projets pour le Manager.

---

## Dev Agent Record

### Agent Model Used

Cursor agent (Claude) — `bmad-dev-story` workflow, 2026-03-29.

### Debug Log References

_(none)_

### Completion Notes List

- **AC1 mapping:** After FFmpeg HTTP 200 + worker `status: ok`, `AudioFile.status` stays **`uploaded`**; `normalized_path` and `duration_s` are set; `transcribed` is only for post-transcripteur workflow. Assignability = `normalized_path is not None` and `validation_error is None`, plus not `in_progress`, and not `transcribed`/`validated` for new assignment (409 on the latter).
- **AC6:** Extended **`GET /v1/projects?include=audio_summary`** with two aggregate queries (counts by status + unassigned normalized count); no N+1 per project.
- **AC5:** **`GET /v1/me/audio-tasks`** — Auth Transcripteur or Admin (Admin documented for support/debug).
- **AC7:** **Deferred** validate/reject — Epic 6.2; no placeholder routes; UI wires when governance endpoints exist.
- **Brownfield DDL** (if `assignments` missing while `audio_files` already exists):

```sql
CREATE TABLE IF NOT EXISTS assignments (
    id SERIAL PRIMARY KEY,
    audio_id INTEGER NOT NULL UNIQUE REFERENCES audio_files(id) ON DELETE CASCADE,
    transcripteur_id VARCHAR(255) NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at TIMESTAMPTZ,
    manager_validated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_assignments_transcripteur_id ON assignments (transcripteur_id);
```

- **FR (résumé implémentation) :** Tableau d’assignation côté API : statut projet + audios enrichis (`assigned_to` / `assigned_at`), assignation Manager/Admin, liste des tâches pour le transcripteur, synthèse audio optionnelle sur la liste des projets ; sémantique FFmpeg alignée PRD (`uploaded` après normalisation).

### File List

- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `.bmad-outputs/implementation-artifacts/2-4-assignment-dashboard.md`

### Change Log

- 2026-03-29 — Story 2.4: Assignment model + dashboard endpoints; FFmpeg success → `uploaded`; tests and api-mapping updated; AC7 defer validate to Epic 6.

---

## Test Coverage Checklist

- [x] Post-FFmpeg status matches AC1 (updated 2.3-style tests)  
- [x] Assign success + eligibility failures  
- [x] Manager vs non-owner + Admin  
- [x] Transcripteur task list + 403 for wrong role  
- [x] `GET .../status` shape & 404  
- [x] Manager summary / extended list (per Task 6 choice)
