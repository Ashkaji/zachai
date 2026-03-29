# Story 4.3: LoRA Fine-tuning Auto-Trigger (Camunda 7)

Status: review

<!-- Ultimate context engine analysis completed — comprehensive developer guide created. -->

## Story

As the **System**,
I want to **detect when the Golden Set counter reaches the configured threshold** (after each successful, non-idempotent ingestion) and **start the Camunda 7 process** that orchestrates the LoRA fine-tuning pipeline,
so that **Whisper improvement runs automatically** without manual intervention and **Story 4.4** can attach workers and deployment steps to an already-defined BPMN process.

---

## Traduction (FR)

**En tant que** système, **je veux** **détecter lorsque le compteur Golden Set atteint le seuil configuré** (après chaque ingestion réussie et non idempotente) et **démarrer le processus Camunda 7** qui orchestre le pipeline de fine-tuning LoRA, **afin que** l’amélioration de Whisper **s’exécute automatiquement** sans intervention manuelle et que la **Story 4.4** puisse brancher les workers et le déploiement sur un processus BPMN déjà défini.

---

## Acceptance Criteria

1. **Threshold semantics (PostgreSQL, single row `GoldenSetCounter` id=1):** After a **real** counter increment inside `persist_golden_set_entry` (i.e. **not** an idempotent short-circuit and **not** the idempotency-race duplicate path), evaluate whether **`previous_count < threshold <= new_count`** using the **locked** row’s values (`with_for_update()` already held in that transaction). **Only then** consider the threshold **newly reached** for this cycle. **Rationale:** Avoid firing Camunda on every subsequent Golden Set row while `count` stays ≥ `threshold` before Story 4.4 resets the counter; avoid double-fires under concurrent writers because evaluation happens inside the same locked transaction as the increment. [Source: `docs/prd.md` §4.6]

2. **Camunda REST start (non-blocking for ingest):** On newly reached threshold, call Camunda 7 **`POST /process-definition/key/{processKey}/start`** with the same **fire-and-forget tolerance** pattern as `POST /v1/projects` (log errors; **never** fail the Golden Set HTTP response because Camunda is down). Use existing `camunda_client` (`httpx.AsyncClient`, `CAMUNDA_REST_URL`). Pass **variables** at minimum: `goldenSetCount` (Integer), `threshold` (Integer), `triggeredAt` (String, ISO-8601 UTC). **Process definition key:** align with PRD — use **`lora-fine-tuning`** as the BPMN `process id` / start key (consistent with PRD name; mirror **`project-lifecycle`** naming style in repo).

3. **BPMN artifact:** Add **`src/bpmn/lora-fine-tuning.bpmn`** (executable process) modeled like `project-lifecycle.bpmn`: **Start → External Service Task** (topic name **`lora-training`**, matching [Source: `docs/architecture.md` §6 example]) → **End**. No need to implement the external worker in this story (Story 4.4). Ensure Camunda can deploy and Cockpit shows the process; a manual start from Cockpit should create an external task visible to a generic fetch worker.

4. **Deploy BPMN at startup:** Extend **`deploy_bpmn_workflows()`** in `main.py` so **both** `project-lifecycle.bpmn` and **`lora-fine-tuning.bpmn`** are deployed (same `deployment-name`, duplicate filtering). Reuse path resolution strategy already used for `project-lifecycle` (local dev vs Docker paths under `bpmn/`).

5. **Observability:** Structured logs when attempting trigger: `golden_set_count`, `threshold`, `process_key`, `camunda_status` or exception class, `process_instance_id` if returned. Never log secrets.

6. **Golden Set status API (doc/code alignment):** Implement **`GET /v1/golden-set/status`** as documented in [Source: `docs/api-mapping.md` §4]: Auth **Manager or Admin**; response shape **`{ "count", "threshold", "last_training_at", "next_trigger_at" }`**. Define `next_trigger_at` as **`null`** in this story (reserved for future scheduler semantics) **or** as a simple computed hint, e.g. `max(0, threshold - count)` entries remaining — **pick one** and document in OpenAPI/description. Read `GoldenSetCounter` id=1; **404** if row missing is optional (prefer **200** with zeros if row auto-created at startup).

7. **Tests (`test_main.py`):** (a) When mocked counter transition crosses threshold, assert **`camunda_client.post`** invoked with path containing **`lora-fine-tuning/start`** and expected variable types. (b) When ingest is idempotent (`idempotent: True`), **no** Camunda start. (c) When increment does not cross threshold, **no** start. (d) When Camunda raises `ConnectError`, Golden Set route still **2xx** and DB/MinIO state remains committed. Reuse existing Camunda mock patterns from project-creation tests.

8. **Scope fence — Story 4.4 only:** Do **not** implement dataset export, GPU training, WER evaluation, MinIO model publish, counter reset, or `POST /v1/callback/model-ready` behavior in this story. Do **not** add Python external-task worker for `lora-training` unless a minimal noop worker is required for CI visibility (prefer **not**; Camunda Cockpit suffices).

9. **Documentation:** Update [Source: `docs/api-mapping.md` §4] so **`POST /v1/golden-set/entry`** text matches behavior: after persist + increment, threshold check **may** start Camunda **`lora-fine-tuning`**. Clarify that **`frontend-correction`** path delegates to the same persistence routine and therefore **inherits** the same trigger behavior.

---

## Tasks / Subtasks

- [x] **Task 1 (Threshold + trigger in persistence path)** — Inside `persist_golden_set_entry` (or a dedicated helper called only from the successful commit path), capture **pre-increment** `count`, apply increment, then evaluate crossing rule; call async Camunda start helper.
- [x] **Task 2 (BPMN + deploy)** — Add `lora-fine-tuning.bpmn`; extend `deploy_bpmn_workflows()` to deploy multiple files.
- [x] **Task 3 (Status endpoint)** — Implement `GET /v1/golden-set/status` with Manager/Admin auth.
- [x] **Task 4 (Tests + docs)** — Extend `test_main.py`; update `api-mapping.md`.

### Review Findings

- [x] [Review][Patch] Camunda start helper must not leak exceptions after DB commit — fixed 2026-03-29: broad `except Exception` + `test_golden_set_internal_entry_camunda_invalid_json_still_2xx`. [src/api/fastapi/main.py:~944-992]
- [x] [Review][Defer] `compose.yml` switch to built `zachai-postgres` / `zachai-keycloak` images (`src/docker/*`) — not listed in story 4.3 scope; reasonable Windows bind-mount workaround; confirm CI/docs mention `docker build` context for `src/`. — deferred, bundled in same branch

---

## Dev Notes

### Scope boundaries

- **In scope:** Threshold detection wired to **real** increments, Camunda **start**, minimal BPMN, dual BPMN deploy, status read API, tests, api-mapping alignment.
- **Out of scope:** LoRA training implementation, model registry updates, counter reset after training, admin notifications, Hocuspocus, Label Studio changes.

### Cross-story dependencies

- **Depends on:** Stories **4.1** and **4.2** — shared `persist_golden_set_entry`, `GoldenSetCounter`, MinIO layout.
- **Unlocks:** Story **4.4** — external task worker(s), training pipeline, WER, deploy to `models/latest`, `last_training_at` updates, counter reset.

### Threshold / config edge cases

- **`GOLDEN_SET_THRESHOLD` env:** Already parsed at startup in `main.py`; `GoldenSetCounter.threshold` is seeded from it for new rows. If ops change env without DB update, document that **DB row `threshold`** is source of truth at runtime unless you add a sync step (not required unless product asks).
- **Invalid threshold ≤ 0:** Story 4.2 deferred strict validation; for 4.3, if `threshold <= 0`, **do not** trigger Camunda (log warning once per crossing attempt or at startup).

### Concurrency

- Counter update already uses **`with_for_update()`** in the ingest path — keep trigger evaluation **inside** that critical section before `commit` so two parallel ingests cannot both “think” they crossed first without serialization.

---

## Technical Requirements

| Area | Requirement |
|------|-------------|
| Camunda | REST start only; same error-tolerance as project lifecycle |
| Transactions | Trigger decision uses locked `GoldenSetCounter` row in same transaction as increment |
| Auth | Status route: Manager / Admin (mirror other manager-scoped routes) |
| Idempotency | Idempotent ingest must **not** bump counter → must **not** trigger |

---

## Architecture Compliance

| Source | Compliance |
|--------|------------|
| `docs/architecture.md` §2 diagram | `API -->|Increment counter| DB` then `API -->|Trigger fine-tuning| C7` |
| `docs/architecture.md` §6 | External task topic **`lora-training`**; deploy BPMN at startup |
| `docs/prd.md` §4.6 | Counter threshold → start **`lora-fine-tuning`** process |

---

## Library / Framework Requirements

- **No new Python dependencies** — `httpx` already in use.
- **Camunda 7** image already in Compose; REST unauthenticated on internal Docker network per architecture warning.

---

## File Structure Requirements

```
src/
├── api/fastapi/
│   ├── main.py              ← MODIFY (threshold logic, deploy, status route, Camunda helper)
│   └── test_main.py         ← MODIFY
├── bpmn/
│   ├── project-lifecycle.bpmn  (existing)
│   └── lora-fine-tuning.bpmn   ← NEW
docs/
└── api-mapping.md           ← MODIFY
```

---

## Testing Requirements

- Mock **`camunda_client.post`** for start calls; use real DB/MinIO mocks consistent with existing Golden Set tests.
- Cover **crossing** vs **not crossing** vs **idempotent** vs **Camunda down**.

---

## Previous Story Intelligence

- **Story 4.2** (`4-2-golden-set-user-loop-frontend-corrections.md`): All Golden Set writes funnel through **`persist_golden_set_entry`**; counter uses **`ctr.count = GoldenSetCounter.count + 1`** after row lock — compute **`previous_count`** from ORM state **before** assigning the new value (or read `ctr.count` before increment). **W7/W8 deferred items** now apply: threshold must be **consumed** responsibly; **api-mapping** currently overstates Camunda trigger on `/entry` — fix in this story.
- **Story 4.1:** Internal secret route and Label Studio webhook both use the same persistence helper — trigger applies to **all** ingestion sources.

---

## Git Intelligence Summary

- Recent commits: Golden Set expert/user loops, OpenVINO/model registry, assignment dashboard. **`deploy_bpmn_workflows`** currently deploys **only** `project-lifecycle.bpmn` — 4.3 must generalize.
- Only BPMN file in `src/bpmn/` today: `project-lifecycle.bpmn`.

---

## Latest Technical Information

- **Camunda 7 Run 7.24.x:** Process start via `/process-definition/key/{key}/start` with JSON body `{"variables": {...}}` — variable format `{"value": x, "type": "Integer"|"String"|...}` matches existing `project-lifecycle` start in `main.py`.
- **EOL:** Architecture notes Camunda 7 EOL — acceptable for current stack; no migration in this story.

---

## Project Context Reference

- No `project-context.md` in repo — use `docs/*.md` and implementation artifacts under `.bmad-outputs/implementation-artifacts/`.

---

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

### Completion Notes List

- Threshold crossing uses `previous_count < db_threshold <= new_count` on the locked `GoldenSetCounter` row; Camunda `start_lora_finetuning_camunda` runs **after** successful `commit` (fire-and-forget; same tolerance pattern as project creation).
- `next_trigger_at` is always `null` in the status API until scheduler semantics exist (Story 4.4+).
- **FR — Résumé :** Seuil Golden Set évalué dans la transaction verrouillée ; démarrage Camunda `lora-fine-tuning` après commit ; BPMN minimal avec tâche externe `lora-training` ; endpoint statut Manager/Admin ; tests `test_main.py` (seuil, idempotence, Camunda down).

### File List

- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `src/bpmn/lora-fine-tuning.bpmn`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-03-29 — Story 4.3 implemented: threshold trigger, Camunda start, dual BPMN deploy, `GET /v1/golden-set/status`, tests, api-mapping alignment; sprint status → review.

---

## Story Completion Status

**review** — Implementation complete; all tasks checked; `pytest test_main.py` passes (108 tests).

---

## Questions / Clarifications (saved for product — optional)

1. Should **`last_training_at`** be touched on **Camunda start** (4.3) or only when training **finishes** (4.4)? **Recommendation:** 4.4 only; status API may return `null` until then.
2. If threshold is **lowered** in DB while `count` is already above new threshold, should we trigger immediately on next increment or require one-shot backfill job? **Recommendation:** document “next crossing only” unless ops manually start Camunda.
