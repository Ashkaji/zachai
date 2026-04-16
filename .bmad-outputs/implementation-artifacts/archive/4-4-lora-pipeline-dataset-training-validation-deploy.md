# Story 4.4: LoRA Fine-tuning Pipeline — Dataset → Training → Validation → Deploy

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created. -->

## Story

As the **System**,
I want to **prepare a training dataset from Golden Set data, run LoRA fine-tuning, evaluate WER on a held-out Golden Set slice, and on success publish a new model version to the MinIO Model Registry** (updating `models/latest` so OpenVINO hot-reloads),
so that **Whisper improves continuously after each threshold-triggered Camunda run** and **`GET /v1/golden-set/status` reflects `last_training_at` and a reset counter** ready for the next flywheel cycle.

---

## Traduction (FR)

**En tant que** système, **je veux** **préparer un jeu d’entraînement à partir du Golden Set, exécuter le fine-tuning LoRA, évaluer le WER sur une partie réservée du Golden Set, et en cas de succès publier une nouvelle version du modèle dans le Model Registry MinIO** (mise à jour de `models/latest` pour le hot-reload OpenVINO), **afin que** Whisper **s’améliore après chaque exécution Camunda déclenchée au seuil** et que **`GET /v1/golden-set/status` reflète `last_training_at` et un compteur réinitialisé** pour le prochain cycle.

### Précisions (FR) — alignées AC4, AC5, AC6 et AC12

- **WER (AC4) :** Le WER s’applique **uniquement au jeu d’évaluation** (hold-out). Pour chaque ligne d’éval, exécuter l’**inférence ASR avec le checkpoint LoRA nouvellement entraîné** sur le segment audio correspondant ; la **référence** est le texte corrigé (`corrected_text`). Calculer le WER avec **jiwer** (ex. au niveau mot — documenter la fonction exacte). Exposer **`werScore`** (Double) et **`werAccepted`** (Boolean), ce dernier valant `true` si et seulement si `werScore <= LORA_MAX_WER` (seuil lu depuis l’environnement dans la tâche d’éval). Ne pas utiliser le WER calculé sur le jeu d’**entraînement** comme métrique de la passerelle Camunda.

- **Publication registre & callback (AC5) :** Ordre obligatoire : **(1)** upload de l’arborescence modèle sous un **préfixe versionné** dans MinIO ; **(2)** mise à jour sûre du pointeur **`models/latest`** vers ce préfixe ; **(3)** appel à **`POST /v1/callback/model-ready`** **uniquement après** la réussite de (1) et (2). **Règle par défaut pour le nom du dossier :** par ex. `models/whisper-cmci-<date UTC>-<id-court>/`, l’identifiant court étant dérivé du **`processInstanceId`** Camunda ou d’un UUID généré à la publication — à documenter. Si (3) échoue après (2), OpenVINO peut recharger avant PostgreSQL : **journaliser en erreur**, autoriser le **retry** du callback ; l’**idempotence** (AC6) évite une double remise à zéro du compteur ; **pas de rollback MinIO** en MVP.

- **Auth callback (AC6) :** Authentification interne calquée sur **`POST /v1/callback/expert-validation`** et **`_verify_shared_secret`** dans `main.py`. **Il n’existe pas** de route **`POST /v1/callback/transcription`** sur la passerelle : ne pas s’y référer. Mise à jour transactionnelle de **`last_training_at`** et **`count = 0`**, avec **idempotence** via `training_run_id` (ou id d’instance de processus).

- **Variables Camunda (AC12) :** Après chaque tâche externe, compléter avec des variables typées : au minimum **`datasetManifestKey`** (ou équivalent), **`trainedModelStagingPrefix`** (ou équivalent), puis **`werScore`** et **`werAccepted`**. La **passerelle exclusive** peut se baser sur **`werAccepted == true`** (recommandé).

---

## Acceptance Criteria

1. **BPMN alignment with PRD Workflow 2** [Source: `docs/prd.md` §5 « Workflow 2 — Pipeline Fine-tuning »]: Replace the single-task `lora-fine-tuning.bpmn` (Story 4.3) with an executable process **`lora-fine-tuning`** that models the pipeline explicitly using **Camunda external service tasks** (same pattern as `provision-label-studio` in `project-lifecycle`). Minimum flow:
   - Start → **Dataset preparation** (external topic, e.g. `lora-dataset-prep`) → **LoRA training** (external topic **`lora-training`**, keep this topic name for continuity with Story 4.3 / `docs/architecture.md` §6) → **WER evaluation** (external topic, e.g. `lora-wer-eval`) → **exclusive gateway** on WER vs configurable threshold →  
     - **Reject path:** end (or admin notify task — may be stubbed as structured log + Camunda incident-friendly failure)  
     - **Accept path:** **registry publish** (external topic, e.g. `lora-registry-publish`) → End  
   **Note:** « Hot-reload OpenVINO » is **passive** once `models/latest` points at the new prefix (Story 3.3 polling) — do not add a fake external task unless you implement a no-op completion handshake; prefer documenting that hot-reload is implicit.

2. **Dataset preparation (worker behavior):** From PostgreSQL `golden_set_entries` (+ join to `audio_files` / `projects` as needed) and MinIO artifacts under the golden-set bucket, build a **deterministic training export** (e.g. manifest JSON listing segment audio keys, text targets, train vs eval split). **Train/eval split policy** must be **documented** (e.g. fixed ratio via env `LORA_EVAL_FRACTION`, stratify by `weight`, or hold out `weight=high` only) and **reproducible** (seeded shuffle). Respect PRD integrity expectations where applicable [Source: `docs/prd.md` §4.6, checksum discipline].

3. **LoRA training step:** Run fine-tuning in an environment suitable for the stack (new worker image or extended worker under `src/workers/`). **MVP tolerance:** If GPU/weights are not available in CI, support a **documented dev/CI stub** (e.g. env `LORA_TRAINING_STUB=true`) that produces a **valid** OpenVINO-compatible artifact tree under a temp path **only in non-production**, while production path runs real training. **Do not** silently stub in production.

4. **WER evaluation:** Use **`jiwer`** (or equivalent agreed in implementation) on the **eval split only**. **Definition:** For each eval row, run **ASR inference using the newly trained LoRA checkpoint** (the artifact produced in the training step) on the corresponding audio segment (clip from normalized audio / MinIO as resolved via `audio_files` + manifest), producing **hypothesis** text; **reference** text is `golden_set_entries.corrected_text`. Compute WER with jiwer (e.g. word-level `wer` — document the exact function and normalization in the worker README). **Do not** report training-split WER as the gateway metric. Emit at least **`werScore`** (Double) for Camunda; the worker should also set **`werAccepted`** (Boolean) = `true` iff `werScore <= LORA_MAX_WER` (read threshold from env inside the eval task) so the BPMN gateway does not depend on float comparisons in the model XML unless you prefer that pattern. **Acceptance threshold** configurable via env **`LORA_MAX_WER`**, default aligned with product direction [Source: `docs/prd.md` NFR « WER ≤ 2% » — document that strict 2% may require tuning].

5. **Registry publish:** On accept path: **(1)** upload the new OpenVINO / IR model tree to MinIO under a **versioned prefix**; **(2)** **atomically or safely** update the **`models/latest`** pointer object body to that prefix (same semantics as `openvino-worker` `normalize_pointer_content` [Source: `src/workers/openvino-worker/main.py`]); **(3)** call FastAPI **`POST /v1/callback/model-ready`** **only after (1) and (2) succeed**. Callback body per [Source: `docs/api-mapping.md` §5]: `{ "model_version", "wer_score", "minio_path" }` (adjust field names to match implemented schema; keep OpenAPI accurate). **Version prefix (default rule):** Unless product defines `major.minor` elsewhere, use a **monotonic, unique folder name** such as `models/whisper-cmci-<UTC-date>-<short-id>/` where `<short-id>` is derived from **Camunda `processInstanceId`** or a UUID generated at publish time; document the chosen scheme in `docs/api-mapping.md` or worker README. **If (3) fails after (2):** OpenVINO may hot-reload before PostgreSQL shows `last_training_at` — **log at error**, support **retry** of the callback; **idempotency** (see AC6) prevents double counter reset; **MVP: do not** roll back MinIO.

6. **FastAPI `POST /v1/callback/model-ready`:** Implement the callback **with internal authentication** mirroring **`POST /v1/callback/expert-validation`** — reuse **`_verify_shared_secret`** and header naming conventions already in `main.py`. (**Note:** There is **no** `POST /v1/callback/transcription` route on the gateway today; do not cite it as the code reference.) Responsibilities:
   - Persist enough metadata for ops (at minimum update **`GoldenSetCounter.last_training_at`** to completion time UTC; **reset `GoldenSetCounter.count` to 0** after successful deploy so threshold crossing logic from Story 4.3 works on the next cycle).
   - Return appropriate HTTP codes; **idempotency** if the same training run reports twice (optional but recommended: include `training_run_id` or process instance id in body).
   - **Never** log secrets.

7. **`GET /v1/golden-set/status`:** **Verify** (Story 4.3 already reads `GoldenSetCounter`) that **`last_training_at`** reflects successful **`model-ready`** completion (ISO-8601 string as today’s schema). Update OpenAPI field descriptions only if behavior or semantics change.

8. **Camunda worker deployment:** Add a **long-polling external-task worker** (extend `src/workers/camunda-worker/` pattern from `provision_label_studio.py` [Source: existing `fetchAndLock` loop]) that subscribes to **all new LoRA topics** in one process or split processes — your choice, but **one Compose service** is preferred for ops simplicity. Wire **`CAMUNDA_REST_URL`**, MinIO credentials, Postgres (if dataset prep reads DB from worker), FastAPI base URL + callback secret via `src/compose.yml` similarly to other workers.

9. **Failure handling:** Training or WER failures should **fail the external task** with Camunda retries / incidents as appropriate; **must not** partially update `models/latest` or reset the Golden Set counter. On WER reject path, counter stays **unchanged** (ops can still ingest; threshold logic unchanged until a successful deploy).

10. **Tests:**  
    - FastAPI: tests for `model-ready` callback (auth, happy path updates `last_training_at` + count reset, invalid body).  
    - Worker / pipeline: at least **unit-level** tests where feasible; integration tests may mock MinIO/Camunda.  
    - Regression: existing Story 4.3 tests for threshold → Camunda start remain green; if BPMN deployment version changes, adjust any string expectations only if necessary.

11. **Documentation:** Update [Source: `docs/api-mapping.md` §5] for `model-ready` (auth header name, exact JSON). Update [Source: `docs/architecture.md`] only if the worker topology or BPMN file list changes materially.

12. **Camunda variable contract (minimum):** So BPMN conditions and Cockpit debugging stay unambiguous, workers **complete** external tasks with typed variables (Camunda `Integer` / `String` / `Double` / `Boolean` as usual). **Minimum expectations:**
    - **Process start** (Story 4.3): `goldenSetCount`, `threshold`, `triggeredAt` — already passed into the process instance.
    - **After `lora-dataset-prep`:** e.g. `datasetManifestKey` (String) or equivalent pointer to the prepared dataset artifact.
    - **After `lora-training`:** e.g. `trainedModelStagingPrefix` (String) or path the next step consumes.
    - **After `lora-wer-eval`:** `werScore` (Double), **`werAccepted`** (Boolean) per AC4.
    - **Exclusive gateway:** Branch on **`werAccepted == true`** (recommended) **or** a documented numeric expression on `werScore` vs a Double variable — pick one and keep BPMN XML valid for Camunda 7.

---

## Tasks / Subtasks

- [x] **Task 1 (BPMN + deploy)** — Expand `src/bpmn/lora-fine-tuning.bpmn` per AC1; verify Camunda deploy at FastAPI startup still picks up the file (`deploy_bpmn_workflows`).

- [x] **Task 2 (LoRA worker service)** — Implement external-task handler(s): dataset prep → train → WER → publish; add Dockerfile/entrypoint if new image; register in `src/compose.yml` with env vars.

- [x] **Task 3 (FastAPI callback + counter semantics)** — Implement `POST /v1/callback/model-ready`, update `GoldenSetCounter`, extend OpenAPI.

- [x] **Task 4 (Status + docs + tests)** — **Verify** `GET /v1/golden-set/status` returns DB-backed `last_training_at` after a successful `model-ready` (already wired in 4.3 unless schema changes); update `docs/api-mapping.md`; document new env vars in `src/.env.example`; add/extend `test_main.py` (+ worker tests if present).

### Review Findings

- [x] [Review][Decision] Confirm MVP policy for production `lora-training` — **Resolved 2026-03-29:** Accept MVP — production keeps failing `lora-training` until a real trainer is integrated; documented in `src/workers/camunda-worker/README.md`.

- [x] [Review][Patch] WER evaluation does not run ASR on eval audio — **Resolved 2026-03-29:** `wer_eval_score_for_items` + `process_wer_eval` — stub mode keeps idealized WER for dev/CI; non-stub fails the task with an explicit “ASR … not implemented” message. Real OpenVINO-per-segment eval remains future work.

- [x] [Review][Patch] Empty eval split yields `wer_score = 0.0` and can accept — **Resolved 2026-03-29:** `lora-wer-eval` fails with a clear error when the eval split is empty.

- [x] [Review][Patch] Unknown Camunda topic in `dispatch_task` only logs a warning — **Resolved 2026-03-29:** unknown `topicName` triggers Camunda `failure` with `retries: 0`.

- [x] [Review][Defer] `model-ready` idempotency insert vs counter update — if the process crashes after `ModelReadyIdempotency` insert but before `commit` updating `GoldenSetCounter`, a retry may return idempotent success without resetting the counter; rare ops edge case. [`src/api/fastapi/main.py` ~2284–2305] — deferred, pre-existing transaction-boundary pattern

---

## Dev Notes

### Scope boundaries

- **In scope:** End-to-end orchestration from Camunda external tasks through registry publish and FastAPI callback; counter reset and `last_training_at`; BPMN structure per PRD; jiwer eval; MinIO `models/latest` update.

- **Out of scope:** Full admin notification product (email/Slack); Hocuspocus; new Frontend screens; replacing Camunda 7; Epic 5+ features.

- **Delivery note:** The story is large; **vertical slices** (e.g. BPMN + stub workers first, then real training) are acceptable if each slice keeps `main` green and meets ACs when combined.

### Cross-story dependencies

- **Depends on:** **4.1–4.3** — `GoldenSetEntry`, MinIO layout, `GoldenSetCounter`, `persist_golden_set_entry`, Camunda start variables (`goldenSetCount`, `threshold`, `triggeredAt`), BPMN `lora-fine-tuning` key.

- **Depends on:** **3.3** — Model Registry bucket, `latest` pointer semantics, OpenVINO hot-reload behavior.

### Architecture naming drift

- `docs/architecture.md` §6 example lists `lora-finetuning.bpmn` (typo vs deployed `lora-fine-tuning.bpmn`). Story 4.4 should **prefer the deployed filename**; optional doc fix if touched.

---

## Technical Requirements

| Area | Requirement |
|------|-------------|
| Camunda | External tasks only for worker steps; use `fetchAndLock` + `complete` / `handleFailure` patterns consistent with `provision_label_studio.py` |
| MinIO | Use same bucket naming as gateway (`models` bucket); pointer key `latest` |
| PostgreSQL | In **`model-ready`**, update **`last_training_at`** and **`count = 0`** in **one committed transaction**; use **`training_run_id`** (or Camunda process instance id) for **idempotency** so retries do not double-reset |
| Security | Callback secret header; internal Docker network only |
| Config | Env for WER threshold, eval fraction, training stub flag (non-prod only) |

---

## Architecture Compliance

| Source | Compliance |
|--------|------------|
| `docs/architecture.md` §B | FastAPI starts processes; workers poll Camunda |
| `docs/architecture.md` §C | `models/latest` → OpenVINO poll |
| `docs/prd.md` §4.6 & §5 Workflow 2 | Pipeline steps and gateway on WER |

---

## Library / Framework Requirements

- **`jiwer`** (WER) — add to relevant worker `requirements.txt` unless using a thin wrapper in FastAPI (prefer worker-side eval to keep GPU/training deps out of API container).
- **MinIO** Python client in worker (same as openvino-worker).
- **httpx** for Camunda + FastAPI callback from worker.

---

## File Structure Requirements

```
src/
├── api/fastapi/
│   ├── main.py              ← MODIFY (callback route, counter updates, OpenAPI)
│   └── test_main.py         ← MODIFY
├── bpmn/
│   └── lora-fine-tuning.bpmn  ← MODIFY (expand process)
├── workers/
│   └── camunda-worker/      ← MODIFY or ADD sibling worker package for LoRA topics
│       ├── Dockerfile
│       ├── requirements.txt
│       └── *.py
├── compose.yml              ← MODIFY (new env vars, worker command if needed)
├── .env.example             ← MODIFY (callback secret, LORA_* env vars, worker URLs)
docs/
└── api-mapping.md           ← MODIFY
```

---

## Testing Requirements

- Mock external services in API tests; use test doubles for MinIO/Camunda in worker unit tests where practical.
- Confirm **no regression** in Golden Set ingest + threshold Camunda start (Story 4.3).

---

## Previous Story Intelligence

- **Story 4.3** (`4-3-lora-finetuning-auto-trigger-camunda.md`): Threshold crossing uses `previous_count < db_threshold <= new_count` inside locked transaction; Camunda start runs **after** `commit`; `next_trigger_at` remains `null`; **`last_training_at` is 4.4’s responsibility**. BPMN today is **only** `lora-training` → End — 4.4 **replaces** that shape with the full pipeline while **keeping** topic `lora-training` for the training step.

- **Story 3.3:** Registry pointer is text body pointing at version prefix; OpenVINO syncs full tree under prefix.

---

## Git Intelligence Summary

- Recent work: Golden Set loops, **4.3** Camunda + dual BPMN deploy, OpenVINO model registry hot-reload (`61fb365`, `3d298c9`, `a171285`).
- **No** existing `model-ready` route in `main.py` — greenfield implementation.
- Camunda worker today only handles **`provision-label-studio`**.

---

## Latest Technical Information

- **Camunda 7 REST:** External task complete/failure APIs unchanged in 7.24.x community.
- **jiwer:** Use current stable release; WER definition (standardize on `wer` word-error rate) documented in dev notes for reproducibility.

---

## Project Context Reference

- No `project-context.md` in repo — use `docs/*.md` and `.bmad-outputs/implementation-artifacts/*.md`.

---

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

### Completion Notes List

- Implemented full `lora-fine-tuning` BPMN: external tasks `lora-dataset-prep` → `lora-training` → `lora-wer-eval` → exclusive gateway on `werAccepted` → `lora-registry-publish` → end (reject path ends without registry/callback).
- `camunda-worker` now runs `run_workers.py` (provision + LoRA loop). LoRA worker: DB manifest export with seeded train/eval split (`LORA_EVAL_FRACTION`, `LORA_SPLIT_SEED`), jiwer WER on eval split, MinIO versioned publish + `latest` pointer (aligned with openvino-worker normalization), callback with retries if MinIO succeeded.
- FastAPI: `ModelReadyIdempotency` table + `POST /v1/callback/model-ready` (`X-ZachAI-Model-Ready-Secret`), resets `GoldenSetCounter.count` and sets `last_training_at`.
- **Production training:** worker fails `lora-training` with a clear error until a real trainer is integrated; non-prod uses `LORA_TRAINING_STUB` + `LORA_STUB_SOURCE_PREFIX` (documented).
- Tests: `test_main.py` (+5 model-ready cases), `camunda-worker/test_lora_pipeline.py` for split/pointer helpers.
- 2026-03-29 follow-up: `wer_eval_score_for_items` — fail on empty eval; non-stub WER fails explicitly; unknown Camunda topic reports `failure`; README MVP production note.

### File List

- `src/bpmn/lora-fine-tuning.bpmn`
- `src/workers/camunda-worker/lora_pipeline.py`
- `src/workers/camunda-worker/run_workers.py`
- `src/workers/camunda-worker/test_lora_pipeline.py`
- `src/workers/camunda-worker/README.md`
- `src/workers/camunda-worker/Dockerfile`
- `src/workers/camunda-worker/requirements.txt`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `src/compose.yml`
- `src/.env.example`
- `docs/api-mapping.md`
- `docs/architecture.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-03-29 — Story 4.4: LoRA BPMN pipeline, combined Camunda worker, model-ready callback, docs and tests.

---

## Story Completion Status

**done** — 2026-03-29: worker fixes merged; MVP documented (stub WER / prod training TBD); real ASR-on-audio WER is a future hardening story if product requires strict AC4.

---

## Questions / Clarifications (optional — for product)

1. Should **failed** training runs decrement or **leave** the Golden Set counter? **Recommendation:** leave unchanged until successful `model-ready` (AC9).
2. If product requires strict **`whisper-cmci-v{major}.{minor}`** instead of the **default date + id prefix** in AC5, specify the authority (DB sequence vs release tag).
