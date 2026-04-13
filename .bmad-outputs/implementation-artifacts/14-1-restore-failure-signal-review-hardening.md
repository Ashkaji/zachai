# Story 14.1: Restore failure signal — code review hardening (post–13.1)

Status: ready-for-dev

## Story

**As a** maintainer of the collaboration stack,

**I want** the Story **13.1** implementation (restore failure broadcast) tightened per the **unresolved code-review findings**,

**So that** exception handling, Redis publish safety, error-code mapping, and editor UX stay **predictable, localizable, and regression-free** without changing the **public contract** (`schema_version`, payload fields, stateless types) unless explicitly versioned.

## Context

- **Source:** Epic 13 retrospective **action A1** — triage [Story 13.1 review findings](13-1-restore-failure-broadcast-collaborators.md#review-findings) (unchecked items).
- **Scope:** Hardening only — **no** new user-facing features beyond fixing incorrect/stale UX and safer backend behavior.
- **Deferred items (do not re-open without new decision):** Network I/O in `finally`, triple fallback UI, z-index escalation strategy (see 13.1 story — marked `[Review][Defer]`).

## Acceptance criteria

### Backend (`src/api/fastapi/main.py`)

1. **`_document_restore_failed_signal` typing & mapping**
   - Replace **risky `BaseException`** in the public signature with a **narrower** type (`Exception` or a union that still allows mapping `HTTPException` and known internal errors), **or** document why `BaseException` is required and ensure **callers never pass** `KeyboardInterrupt` / `SystemExit` in practice.
   - Add explicit handling for **`AttributeError`** (and similar) so they map to a **stable** `DocumentRestoreFailureCode` instead of falling through to **`UNKNOWN`** when a more specific code is appropriate.
   - Remove or replace **brittle substring checks** on `HTTPException` detail (e.g. `"snapshot" in el`) with **structured detail** (e.g. stable `error` / `code` field from raised `HTTPException`s in the restore core) **or** centralize string parsing in one helper with **tests** for each branch.

2. **`HTTPException.detail` handling**
   - Handle all **relevant** `detail` shapes used in restore paths (`dict`, `str`, **and** nested structures if any) so **`code` / `message` in `document_restore_failed`** are deterministic and safe for clients (no raw stack traces).

3. **`finally` block / Redis publish safety**
   - Ensure **failure publish** and **`document_unlocked`** do not create **races or double publishes** that confuse ordering guarantees tested in `test_story_12_3.py`.
   - If multiple awaits run in `finally`, document **ordering** and consider **guards** so unlock still runs if failure publish fails (existing `try/except` around failure publish should remain; extend if review concern was concurrent overlapping calls).

### Frontend (`src/frontend/src/editor/TranscriptionEditor.tsx`)

4. **Stale failure alert**
   - Fix the case where a **remote restore failure banner** can remain visible when a **successful** restore completes (review: stale failure on success). Verify paths: **`zachai:document_restored`**, reconnect/sync, and local successful restore flow.

5. **i18n / copy**
   - Replace **hardcoded English** strings in `REMOTE_RESTORE_FAILURE_BY_CODE` with the project’s **existing i18n pattern** (same approach as other editor strings), or add a **minimal** `useTranslation` (or equivalent) usage **consistent with this file**.

6. **Style debt (non-deferred)**
   - Reduce **inline styles / magic z-index** for the Story 13.1 failure banner **only if** it can align with **existing** Azure/editor patterns **without** reopening the deferred **global** z-index strategy (keep scope local to this banner).

### Tests

7. Extend **`src/api/fastapi/test_story_12_3.py`** (and frontend tests if present) to cover:
   - New **`HTTPException.detail`** branches and **non-HTTP** exception mapping into `document_restore_failed`.
   - Any new **structured detail** fields on raised exceptions (assert JSON published to Redis contains expected `code`).

## Tasks / Subtasks

- [ ] **Backend:** Refine `_document_restore_failed_signal` and restore-core exception mapping per AC 1–3.
- [ ] **Frontend:** Stale-banner fix + i18n for failure map per AC 4–5; optional style cleanup per AC 6.
- [ ] **Tests:** Pytest updates per AC 7; manual or automated check for stateless ordering unchanged.

## Dev notes

| Area | Path |
|------|------|
| Signal builder & restore core | `src/api/fastapi/main.py` — `_document_restore_failed_signal`, `_restore_document_from_snapshot_core` |
| Editor stateless handler | `src/frontend/src/editor/TranscriptionEditor.tsx` — `hp.on("stateless", …)`, `remoteRestoreFailureMessage` |
| Tests | `src/api/fastapi/test_story_12_3.py` |

- **Contract freeze:** Do **not** rename `zachai:document_restore_failed` or Redis `type: document_restore_failed` without bumping **`schema_version`** and updating **`docs/api-mapping.md`** §15.
- **Regression anchor:** Run `pytest src/api/fastapi/test_story_12_3.py -q` after backend edits.

## References

- [Story 13.1 — Review Findings](13-1-restore-failure-broadcast-collaborators.md#review-findings)
- [Epic 13 retrospective — Action A1](epic-13-retro-2026-04-13.md)
- `docs/api-mapping.md` — stateless messages (Editor & collaboration)

---

## Dev Agent Record

### Agent Model Used

_(To be filled at implementation)_

### Completion Notes List

_(To be filled at implementation)_

### File List

_(To be filled at implementation)_

---

## Traduction française (référence)

**En tant que** mainteneur, **je veux** que l’implémentation du signal d’échec de restauration (Story 13.1) soit **renforcée** selon les points de revue encore ouverts, **afin que** la gestion des exceptions, la publication Redis, le mapping des codes d’erreur et l’UX éditeur restent **fiables** et **cohérentes**, sans changer le contrat public sans versionnement.

**Critères :** affiner le typage et le mapping côté API, sécuriser le `finally`, corriger l’alerte obsolète après succès, internationaliser les libellés, tests étendus.
