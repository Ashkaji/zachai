# Story 14.1: Restore failure signal — code review hardening (post–13.1)

Status: ready-for-dev

<!-- Ultimate context engine analysis completed — comprehensive developer guide created -->

## Story

**As a** maintainer of the collaboration stack,

**I want** the Story **13.1** implementation (restore failure broadcast) tightened per the **unresolved code-review findings**,

**So that** exception handling, Redis publish safety, error-code mapping, and editor UX stay **predictable, localizable, and regression-free** without changing the **public contract** (`schema_version`, payload fields, stateless types) unless explicitly versioned.

## Context

- **Epic 14** (planning): Harden 13.1 per open review items — **no** new product feature, **no** unversioned public contract change [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 14, Story 14.1].
- **Source checklist:** [Story 13.1 — Review Findings](13-1-restore-failure-broadcast-collaborators.md#review-findings) (unchecked `[Review][Patch]` rows).
- **Retro:** Epic 13 action **A1** — triage those findings into this story [Source: `.bmad-outputs/implementation-artifacts/epic-13-retro-2026-04-13.md`].
- **Explicitly out of scope (do not re-open):** Items marked `[Review][Defer]` on 13.1 (network I/O in `finally`, triple fallback UI, global z-index strategy).

## Acceptance criteria

### Backend (`src/api/fastapi/main.py`)

1. **`_document_restore_failed_signal` typing & mapping** — anchor: `src/api/fastapi/main.py` (function body ~3848–3897; payload assembly ~3889–3897).
   - **`BaseException`:** Replace with a **narrower** type in the public signature (`Exception` or a documented union), **or** keep `BaseException` only with an **explicit, reviewed** rationale and guarantees that `KeyboardInterrupt` / `SystemExit` never reach this path from restore.
   - **`AttributeError` / non-HTTP:** Today non-`HTTPException` branches always map to **`UNKNOWN`** with a generic English message (`main.py` ~3884–3887). Extend mapping so **recoverable** attribute/access errors (and similar) get a **stable** `DocumentRestoreFailureCode` where appropriate, without leaking internals in `message`.
   - **Brittle substring mapping:** Replace `"snapshot" in el`, `"integrity" in el`, etc. (~3861–3877) with **structured** `HTTPException.detail` (e.g. stable `code` / `error` keys from raise sites in `_restore_document_from_snapshot_core`) **or** one **tested** normalization helper; avoid scattering string heuristics.

2. **`HTTPException.detail` handling** (~3853–3883)
   - Cover **all** shapes used on restore paths: `dict` (with nested values if any), `str`, `list`/`tuple` — deterministically derive **`code`** / **`message`** for Redis. Never forward stack traces or MinIO keys [Source: Story 13.1 — Security / UI copy].

3. **`finally` / ordering** (~4010–4021)
   - Preserve **documented ordering:** `document_restore_failed` **before** `document_unlocked` when `locked_signaled` and `pending_exc` is set; then unlock + lock delete.
   - Ensure **no double or racy publishes** that break tests expecting this sequence. If failure publish fails, **unlock must still run** (existing `try/except` around failure publish — extend only if review identified a gap).

### Frontend (`src/frontend/src/editor/TranscriptionEditor.tsx`)

4. **Stale failure alert**
   - Fix **remote** failure banner remaining after a **successful** restore (13.1 review). **`zachai:document_restored`** already clears `remoteRestoreFailureMessage` (`TranscriptionEditor.tsx` ~576–578) — audit **all** success paths (local restore completion, reconnect, ticket refresh) so no edge case leaves the banner (~1447–1481) visible incorrectly.

5. **i18n / copy**
   - Replace hardcoded **`REMOTE_RESTORE_FAILURE_BY_CODE`** strings (~50–58) and banner title **"Restoration failed"** / **"Dismiss"** (~1468–1479) with the **same i18n mechanism** as the rest of the editor (grep nearby strings for the project pattern).

6. **Style debt (bounded)**
   - Reduce **inline styles / magic z-index** for the failure banner (~1447–1465) only where it aligns with **existing** `za-*` / Azure patterns **without** reopening deferred global z-index work.

### Tests & contract

7. Extend **`src/api/fastapi/test_story_12_3.py`** so that:
   - New **structured** `detail` branches and **non-HTTP** exceptions produce expected **`code`** in published `document_restore_failed` JSON.
   - Ordering vs **`document_unlocked`** remains as today (regression anchor).

8. **Contract freeze:** Do **not** rename Redis `type: document_restore_failed` or client `zachai:document_restore_failed`; do **not** remove `schema_version`, `document_id`, `code`, optional `message`. Any breaking field change requires **`DOCUMENT_RESTORE_FAILED_SCHEMA_VERSION` bump** + **`docs/api-mapping.md`** §15 + coordinated frontend [Source: `main.py` ~3825–3826, `docs/api-mapping.md`].

## Tasks / Subtasks

- [ ] **Backend:** Refine `_document_restore_failed_signal` + restore-core raises per AC 1–3, 8.
- [ ] **Frontend:** Stale-banner audit + i18n per AC 4–5; optional local style cleanup per AC 6.
- [ ] **Tests:** Pytest updates per AC 7 — run `pytest src/api/fastapi/test_story_12_3.py -q`.

## Dev notes

| Area | Path |
|------|------|
| Signal builder & restore core | `src/api/fastapi/main.py` — `DocumentRestoreFailureCode`, `_document_restore_failed_signal`, `_restore_document_from_snapshot_core` |
| Hocuspocus fan-out | `src/collab/hocuspocus/src/index.ts` — only if contract accidentally diverges (should **not** be required for 14.1) |
| Editor stateless handler + banner | `src/frontend/src/editor/TranscriptionEditor.tsx` — `hp.on("stateless", …)`, `remoteRestoreFailureMessage` |
| Tests | `src/api/fastapi/test_story_12_3.py` |

### Previous story intelligence (13.1 → 14.1)

| 13.1 Review finding | Maps to |
|---------------------|--------|
| Risky `BaseException` on `_document_restore_failed_signal` | AC 1 |
| Unprotected / concurrent concerns in `finally` | AC 3 |
| Incomplete `HTTPException.detail` handling | AC 2 |
| Stale failure alert on successful restoration | AC 4 |
| Inline styles / z-index on banner | AC 6 (optional, local) |
| Missing `AttributeError` mapping | AC 1 |
| Hardcoded English in `REMOTE_RESTORE_FAILURE_BY_CODE` | AC 5 |
| Brittle string-matching for codes | AC 1–2 |

**Deferred on 13.1 (do not scope 14.1):** Network I/O in `finally`, triple fallback in UI rendering, global z-index strategy.

### Git intelligence

- Story **13.1** landed as **`49523d5`** (`feat(collab): Story 13-1 restore failure signal for collaborators`) touching `main.py`, Hocuspocus, `TranscriptionEditor.tsx`, `test_story_12_3.py`.
- **14.1** is a **follow-up hardening** PR; keep commits focused and run the same pytest module after backend edits.

### Architecture compliance

- Redis channel **`hocuspocus:signals`** remains the integration point; extend **payload content** only, not parallel channels [Source: Story 13.1 — Architecture compliance].
- **423** on editor ticket when restore lock held must remain intact (`test_editor_ticket_423_when_restore_lock_held` or equivalent).

### Library / framework requirements

- **Backend:** Existing FastAPI / Starlette `HTTPException` patterns; no new dependencies for mapping.
- **Frontend:** Use **existing** i18n stack already in the app; do not introduce a second translation system.

### Testing standards

- **Primary:** `pytest src/api/fastapi/test_story_12_3.py -q`.
- Frontend: add or extend tests **only if** the project already has editor/component tests for `TranscriptionEditor`; do not block on new E2E unless already standard.

### Project structure notes

- No new top-level docs files unless `api-mapping.md` §15 must change for a **version bump** (AC 8).

## References

- [Story 13.1 spec + Review Findings](13-1-restore-failure-broadcast-collaborators.md)
- [Epic 13 retrospective — A1](epic-13-retro-2026-04-13.md)
- [Epic 14 / Story 14.1 planning](../planning-artifacts/epics.md) — § Epic 14
- `docs/api-mapping.md` — stateless / Editor & collaboration (§15)

---

## Dev Agent Record

### Agent Model Used

_(To be filled at implementation)_

### Debug Log References

### Completion Notes List

### File List

---

## Traduction française (référence)

**En tant que** mainteneur, **je veux** que l’implémentation du signal d’échec de restauration (Story 13.1) soit **renforcée** selon les points de revue encore ouverts, **afin que** la gestion des exceptions, la publication Redis, le mapping des codes d’erreur et l’UX éditeur restent **fiables** et **localisables**, sans modifier le contrat public sans versionnement explicite.

**Critères :** affiner le typage et le mapping côté API ; traiter les formes de `detail` ; sécuriser l’ordre dans le `finally` ; corriger toute alerte obsolète après succès ; internationaliser les libellés ; tests étendus dans `test_story_12_3.py`.
