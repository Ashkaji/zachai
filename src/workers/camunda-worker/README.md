# Camunda external-task workers

- **`provision_label_studio.py`** — topic `provision-label-studio` (Story 2.2).
- **`lora_pipeline.py`** — topics `lora-dataset-prep`, `lora-training`, `lora-wer-eval`, `lora-registry-publish` (Story 4.4).

`run_workers.py` runs both asyncio loops in one container.

## LoRA pipeline / WER (jiwer)

Eval split: rows from `golden_set_entries` are shuffled with **`LORA_SPLIT_SEED`**. The eval set size is `round(n × LORA_EVAL_FRACTION)`, capped so at least one row stays in the training split when `n > 1`.

WER on the eval split uses **`jiwer.wer`** on the **concatenated** reference and hypothesis strings (word-level error rate, **0–1**). **`LORA_MAX_WER`** uses the same scale (e.g. `0.02` = 2%). **`werAccepted`** is `wer_score <= LORA_MAX_WER`.

In **`LORA_TRAINING_STUB=true`** (non-production only), “ASR” for WER is idealized (hypothesis = reference), so eval WER is **0** if there are eval rows; training still copies an existing OpenVINO tree from **`LORA_STUB_SOURCE_PREFIX`** in the **models** bucket into a staging prefix.

If **`LORA_TRAINING_STUB=false`**, the `lora-wer-eval` task **fails** until real ASR-on-audio is integrated (no silent “perfect” WER). **`ENVIRONMENT=production`/`prod`** already fails **`lora-training`** until a real trainer is wired — that is an intentional MVP gap (documented product decision 2026-03-29).

The eval split must contain **at least one row**; otherwise `lora-wer-eval` fails (e.g. single Golden Set row yields no eval hold-out with the default split policy).

## Environment (LoRA)

| Variable | Purpose |
|----------|---------|
| `MODEL_READY_CALLBACK_SECRET` | Header `X-ZachAI-Model-Ready-Secret` for `POST /v1/callback/model-ready` |
| `FASTAPI_INTERNAL_URL` | Gateway base URL (e.g. `http://fastapi:8000`) |
| `LORA_MAX_WER` | Accept threshold (default `0.02`) |
| `LORA_EVAL_FRACTION` | Eval fraction (default `0.2`) |
| `LORA_SPLIT_SEED` | Reproducible shuffle (default `42`) |
| `LORA_TRAINING_STUB` | `true` in dev/CI only — copy stub IR tree |
| `LORA_STUB_SOURCE_PREFIX` | Version prefix inside **models** bucket (with trailing `/`) |
| `ENVIRONMENT` | `production` / `prod` forbids `LORA_TRAINING_STUB` |

`compose.yml` passes `LORA_STUB_SOURCE_PREFIX=whisper-base-ov/` by default. If **`LORA_TRAINING_STUB` is unset or empty**, `lora_pipeline.py` enables stub mode only when **`ENVIRONMENT` is not** `production`/`prod` (so production + forgotten stub does not crash the worker). A copied **`.env.example`** still sets `LORA_TRAINING_STUB=true` explicitly for local runs. **Production** with an **explicit** `LORA_TRAINING_STUB=true` still fails at startup (stub is forbidden in prod).
