# Bible text sources — maintainer documentation

**Entry point** for legal, licensing, and provenance metadata used by Epic 15 (Bible data pipeline). Downstream API references: `GET /v1/bible/verses`, `POST /v1/bible/ingest`, translation codes such as **LSG** and **KJV** (see [`docs/api-mapping.md`](../api-mapping.md) §17).

---

## Purpose

- Keep **one place** in the repository that explains which Bible editions the project may ingest, under what terms, and how raw files are pinned (paths + hashes) for reproducibility and audits.
- Support **FR27** (Bible text pipeline): licensed texts only, reproducible pipeline, **no live Bible API in production** (see planning epics).

---

## Scope: this folder vs Story 15.2 / 15.3

| Story | Scope |
|--------|--------|
| **15.1** (this folder) | Documentation and provenance metadata only: entrypoint, license register, manifest (paths, SHA-256 placeholders, license cross-references). **No** conversion scripts, **no** operator runbook, **no** ingestion code changes. |
| **15.2** | Extract/convert approved sources into JSON compatible with `src/scripts/ingest_bible.py` and `_normalize_bible_book` in the API. |
| **15.3** | Smoke tests, operator steps for `POST /v1/bible/ingest`, secrets, and verification. |

---

## Where raw files live

- **Recommended layout (not created by 15.1):** `data/bible/sources/<translation_code>/` under the repo root, with one subdirectory per translation or edition you pin for ingest.
- **Git:** Heavy archives and uncompressed data are **not** committed by default. This repo ignores common archive/binary patterns (e.g. `*.zip`, `*.tar*`, `*.gz`, `*.7z`) as well as `*.xml` and `*.txt` under data directories (see [`.gitignore`](../../.gitignore) — *Heavy Assets & Data*). Operators keep downloads **outside git** or use **Git LFS** only if your org policy allows and licenses permit redistribution of LFS objects.
- **Never commit:** Secrets, license keys, or paywalled files that violate terms.

---

## Contents of this folder

| File | Role |
|------|------|
| [`LICENSES.md`](LICENSES.md) | Per-translation/edition license summary and compatibility with **local PostgreSQL storage** + **HTTP API** serving. |
| [`SOURCES.md`](SOURCES.md) | Provenance manifest (paths, SHA-256, version labels, links to license rows). |

---

## Operator Runbook (Story 15.3)

This section provides the exact commands for ingestion, required environment variables (secrets), and the expected local file structure to populate the `bible_verses` table in PostgreSQL.

### Prerequisites

1.  **FastAPI Backend:** The backend must be running (usually on `http://localhost:8000`).
2.  **Internal Secret:** You must have the `GOLDEN_SET_INTERNAL_SECRET`. This secret is required for the `X-ZachAI-Golden-Set-Internal-Secret` header. It should be set in your `.env` file or passed as a CLI argument.
3.  **JSON Source Files:** The converted Bible JSON files should be located in `data/bible/json/`.

### Ingestion Commands

To ingest a Bible translation, use the `src/scripts/ingest_bible.py` script:

```bash
# Ingest Louis Segond (LSG)
python3 src/scripts/ingest_bible.py data/bible/json/lsg.json \
  --url http://localhost:8000 \
  --secret YOUR_GOLDEN_SET_INTERNAL_SECRET \
  --translation LSG

# Ingest King James Version (KJV)
python3 src/scripts/ingest_bible.py data/bible/json/kjv.json \
  --url http://localhost:8000 \
  --secret YOUR_GOLDEN_SET_INTERNAL_SECRET \
  --translation KJV
```

### Ingest auth checks (internal secret)

`POST /v1/bible/ingest` is protected by `verify_golden_set_internal_secret` (see `src/api/fastapi/main.py`). The request body must satisfy `BibleIngestRequest` (**at least one verse**) before the handler runs; an empty `verses` array returns **422**, not an auth error.

Quick checks against a running API (`BASE` defaults to `http://localhost:8000`); use a minimal placeholder verse for auth-only probes:

```bash
BASE="${BASE:-http://localhost:8000}"
BODY='{"verses":[{"translation":"LSG","book":"Jean","chapter":3,"verse":16,"text":"probe"}]}'

# No X-ZachAI-Golden-Set-Internal-Secret header → 401 Unauthorized
curl -sS -o /dev/null -w "%{http_code}\n" -X POST "${BASE}/v1/bible/ingest" \
  -H "Content-Type: application/json" \
  -d "$BODY"

# Wrong secret → 403 Forbidden
curl -sS -o /dev/null -w "%{http_code}\n" -X POST "${BASE}/v1/bible/ingest" \
  -H "Content-Type: application/json" \
  -H "X-ZachAI-Golden-Set-Internal-Secret: not-the-configured-secret" \
  -d "$BODY"
```

### Verification (Smoke Test)

After ingestion, run the smoke test to verify that `GET /v1/bible/verses` returns the expected **Golden Verse** snippets for LSG and KJV (200 + body match). The script requires **all** checks to pass; exit code is non-zero if any verse is missing or mismatched.

**Redis cache (Story 13.2):** Successful ingest increments the per-translation generation in Redis when `BIBLE_VERSE_CACHE_ENABLED` is on, so cache keys rotate and clients do not keep serving stale payloads. This script does not inspect Redis; to validate end-to-end after you change text and re-ingest, run the smoke test again and confirm snippets still match the database.

```bash
# Set your JWT (from a logged-in session or test user)
export ZACHAI_TEST_JWT="your_jwt_here"

# Run the smoke test
python3 src/scripts/smoke_test_bible.py --url http://localhost:8000
```

### Expected File Structure

```text
zachai/
├── data/
│   └── bible/
│       └── json/
│           ├── lsg.json
│           └── kjv.json
└── src/
    └── scripts/
        ├── ingest_bible.py
        └── smoke_test_bible.py
```

---

## Reproducing checksums

After you obtain a source file, record its digest before conversion:

```bash
sha256sum "/path/to/your/downloaded/file"
# macOS: shasum -a 256 "/path/to/your/downloaded/file"
```

Update [`SOURCES.md`](SOURCES.md) with the exact hash of the bytes you use for ingestion so CI and humans can detect drift on re-ingest.

---

## Traduction (FR)

**Point d’entrée** pour la documentation juridique et la provenance des textes bibliques (Epic 15). Les codes de traduction **LSG** et **KJV** sont alignés avec [`docs/api-mapping.md`](../api-mapping.md) §17.

**Périmètre Story 15.1 :** uniquement la documentation et le manifeste (chemins, empreintes, références de licence). Les scripts de conversion (15.2) et le runbook opérateur (15.3) viendront plus tard.

**Fichiers bruts :** emplacement conseillé `data/bible/sources/` ; les archives lourdes restent en général **hors dépôt** ou **LFS** selon la politique interne — voir [`.gitignore`](../../.gitignore).

Pour les sommaires de licence et le tableau de provenance, voir [`LICENSES.md`](LICENSES.md) et [`SOURCES.md`](SOURCES.md).
